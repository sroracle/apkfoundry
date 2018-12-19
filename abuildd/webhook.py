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

import abuildd.connections as conn
import abuildd.events as enqueue
from abuildd.builders import ArchCollection
from abuildd.config import CONFIGS, GLOBAL_CONFIG
from abuildd.mqtt import mqtt_watch_builders
from abuildd.utility import assert_exists as _assert_exists
from abuildd.utility import get_command_output, run_blocking_command

FAKE_COMMIT_ID = "0000000000000000000000000000000000000000"

LOGGER = logging.getLogger("abuildd")
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

HOOKS = {
    "Push Hook": (
        "push",
        "repository/git_http_url",
        enqueue.PushEvent.fromGLWebhook
    ),
    "Merge Request Hook": (
        "merge_request",
        "object_attributes/target/http_url",
        enqueue.MREvent.fromGLWebhook
    ),
    "Note Hook": (
        "note", "merge_request/target/http_url",
        enqueue.NoteEvent.fromGLWebhook
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
        try:
            event = HOOKS[hook][2](project, config, data, loop)
        except json.JSONDecodeError as e:
            bad_request(f"HTTP payload: {e.msg}")

        if event:
            async with app["pgpool"].acquire() as db:
                await event.enqueue(db, app["mqtt"], app["builders"])

    return web.Response(text="OK")

def handle_bg_exception(future):
    # TODO: exit if exception raised!
    if future.exception():
        # Raise the suppressed exception
        future.result()

async def start_bg_tasks(app):  # pylint: disable=redefined-outer-name
    app["builders"] = {}
    for arch in GLOBAL_CONFIG["builders"]["arches"].split("\n"):
        app["builders"][arch] = ArchCollection(loop=app.loop)

    app["mqtt_watcher"] = app.loop.create_task(
        mqtt_watch_builders(app["mqtt"], app["builders"]))
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
        conn.init_conns(app.loop))
    app.on_startup.append(start_bg_tasks)
    app.on_cleanup.append(end_bg_tasks)
    web.run_app(app, port=GLOBAL_CONFIG.getint("web", "port"))
