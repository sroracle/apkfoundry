#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2018 Max Rees
# See LICENSE for more information.
import asyncio      # get_event_loop
import configparser # ConfigParser
import json         # JSONDecodeError
import logging      # basicConfig, getLogger
from pathlib import Path

import aiohttp.web as web

import abuildd.enqueue as enqueue
from abuildd.config import CONFIGS, GLOBAL_CONFIG
from abuildd.utility import assert_exists as _assert_exists
from abuildd.utility import get_command_output, run_blocking_command

FAKE_COMMIT_ID = "0000000000000000000000000000000000000000"

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(GLOBAL_CONFIG["webhook"]["loglevel"])
logging.basicConfig(format='%(asctime)-15s %(levelname)s %(message)s')

ROUTES = web.RouteTableDef()

def assert_exists(*args, **kwargs):
    try:
        return _assert_exists(*args, **kwargs)
    except json.JSONDecodeError as e:
        bad_request(f"HTTP payload: {e.msg}")

def bad_request(msg):
    LOGGER.error(msg)
    raise web.HTTPBadRequest(reason=msg)

def unauthorized(msg):
    LOGGER.error(msg)
    raise web.HTTPUnauthorized(reason=msg)

async def handle_push(project, config, data):
    before = assert_exists(data, "before", str)
    after = assert_exists(data, "after", str)
    branch = assert_exists(data, "ref", str)
    url = assert_exists(data, "repository/git_http_url", str)
    user = assert_exists(data, "user_email", str)

    if before == FAKE_COMMIT_ID:
        before = None

    if after == FAKE_COMMIT_ID:
        LOGGER.debug(f"[{project}] Skipping push for deleted ref {branch}")
        return None

    if not branch.startswith("refs/heads/"):
        LOGGER.debug(f"[{project}] Skipping push for non-branch ref {branch}")
        return None
    branch = branch.replace("refs/heads/", "", 1)

    LOGGER.info(f"[{project}] Push: {branch} {before}..{after}")

    job = enqueue.PushJob(project, config, url, branch, after, user)
    job.before = before
    return job

async def handle_merge_request(project, config, data):
    state = assert_exists(data, "object_attributes/state", str)

    if state not in ("opened", "reopened"):
        # Specifically we don't care about state == closed. I'm not sure
        # if there are other states possible.
        LOGGER.debug(f"[{project}] Skipping merge event with state {state}")
        return None

    mr = assert_exists(data, "object_attributes/iid", int)
    # GitLab 8: force pushes to MRs do not update the merge-request/x/head refs
    url = assert_exists(data, "object_attributes/source/http_url", str)
    branch = assert_exists(data, "object_attributes/source_branch", str)
    target = assert_exists(data, "object_attributes/target_branch", str)
    commit = assert_exists(data, "object_attributes/last_commit/id", str)
    user = assert_exists(data, "user/username", str)

    LOGGER.info(f"[{project}] Merge #{mr}: up to {commit} -> {target}")

    job = enqueue.MRJob("merge_request", project, config, url, branch, commit, user)
    job.mr = mr
    job.target = target
    return job

async def handle_note(project, config, data):
    note_type = assert_exists(data, "object_attributes/noteable_type", str)
    if note_type != "MergeRequest":
        LOGGER.debug(f"[{project}] Skipping note with type {note_type}")
        return None

    content = assert_exists(data, "object_attributes/note", str)
    if config["note"]["keyword"] not in content:
        return None

    mr = assert_exists(data, "merge_request/iid", int)
    # GitLab 8: force pushes to MRs do not update the merge-request/x/head refs
    url = assert_exists(data, "merge_request/source/http_url", str)
    branch = assert_exists(data, "merge_request/source_branch", str)
    target = assert_exists(data, "merge_request/target_branch", str)
    commit = assert_exists(data, "merge_request/last_commit/id", str)
    user = assert_exists(data, "user/username", str)

    LOGGER.info(f"[{project}] Note #{mr}: up to {commit} -> {target}")

    job = enqueue.MRJob("note", project, config, url, branch, commit, user)
    job.mr = mr
    job.target = target
    return job

HOOKS = {
    "Push Hook": (
        "push",
        "repository/git_http_url",
        handle_push
    ),
    "Merge Request Hook": (
        "merge_request",
        "object_attributes/target/http_url",
        handle_merge_request
    ),
    "Note Hook": (
        "note", "merge_request/target/http_url",
        handle_note
    ),
}

@ROUTES.post(GLOBAL_CONFIG["webhook"]["endpoint"])
async def handle_webhook(request):
    if "X-Gitlab-Event" not in request.headers:
        bad_request("Missing X-Gitlab-Event header")

    hook = request.headers["X-Gitlab-Event"]
    if hook not in HOOKS:
        bad_request(f"Unsupported hook type {hook}")

    try:
        data = await request.json()
    except json.JSONDecodeError as e:
        bad_request(f"HTTP payload: {e.msg}")

    project = assert_exists(data, HOOKS[hook][1], str)
    project = project.replace("https://", "", 1)
    project = project.replace("/", ".")
    if project == "global":
        bad_request("Project name cannot be exactly 'global'")

    object_kind = assert_exists(data, "object_kind", str)
    kind = HOOKS[hook][0]
    if object_kind != kind:
        bad_request(f"[{project}] Mismatched event types {kind} and {kind}")

    if not project in CONFIGS:
        if not Path(project).is_dir():
            raise bad_request(f"Unknown project {project}")

        CONFIGS[project] = configparser.ConfigParser(interpolation=None)
        CONFIGS[project].read_dict(GLOBAL_CONFIG)

        try:
            await run_blocking_command(
                ["git", "-C", project, "fetch", "origin",
                 "master:master"])
            project_conf = await get_command_output(
                ["git", "-C", project, "show", "master:.abuildd.ini"])
            CONFIGS[project].read_string(project_conf)
        except RuntimeError as e:
            LOGGER.debug(f"Could not find .abuildd.ini: {e}")

    config = CONFIGS[project]

    if config.getboolean(kind, "enabled"):
        job = await HOOKS[hook][2](project, config, data)
        if job:
            job.loop = app.loop
            async with app["pgpool"].acquire() as db:
                await job.enqueue(db, app["mqtt"], app["builders"])

    return web.Response(text="OK")

def handle_bg_exception(future):
    # TODO: exit if exception raised!
    if future.exception():
        # Raise the suppressed exception
        future.result()

async def start_bg_tasks(app):  # pylint: disable=redefined-outer-name
    app["builders"] = {}
    for arch in GLOBAL_CONFIG["builders"]["arches"].split("\n"):
        app["builders"][arch] = enqueue.ArchCollection(loop=app.loop)

    app["mqtt_watcher"] = app.loop.create_task(
        enqueue.mqtt_watch_servers(app["mqtt"], app["builders"]))
    app["mqtt_watcher"].add_done_callback(handle_bg_exception)

async def end_bg_tasks(app):  # pylint: disable=redefined-outer-name
    await app["mqtt"].unsubscribe(["builders/#"])
    await app["mqtt"].disconnect()
    app["mqtt_watcher"].cancel()
    await app["mqtt_watcher"]

    await app["pgpool"].close()

if __name__ == "__main__":
    # pylint: disable=invalid-name
    app = web.Application()
    app.add_routes(ROUTES)
    loop = asyncio.get_event_loop()
    app["pgpool"], app["mqtt"] = loop.run_until_complete(
        enqueue.init_conns(app.loop))
    app.on_startup.append(start_bg_tasks)
    app.on_cleanup.append(end_bg_tasks)
    web.run_app(app, port=GLOBAL_CONFIG.getint("web", "port"))
