#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2018 Max Rees
# See LICENSE for more information.
import asyncio      # get_event_loop
import json         # JSONDecodeError
import logging      # basicConfig, getLogger
from pathlib import Path

import aiohttp.web as web

import abuildd.connections as conn
from abuildd.events import PushEvent, MREvent, NoteEvent
from abuildd.config import ConfigParser, GLOBAL_CONFIG
from abuildd.enqueue import setup_arch_queue
from abuildd.mqtt import mqtt_watch_builders
from abuildd.utility import assert_exists as _assert_exists_orig
from abuildd.utility import get_command_output, run_blocking_command

_CONFIGS = {}
_LOGGER = logging.getLogger(__name__)
ROUTES = web.RouteTableDef()

def _assert_exists(*args, **kwargs):
    try:
        return _assert_exists_orig(*args, **kwargs)
    except json.JSONDecodeError as e:
        _bad_request(f"HTTP payload: {e.msg}")

def _bad_request(msg):
    _LOGGER.error(msg)
    raise web.HTTPBadRequest(reason=msg)

HOOKS = {
    "Push Hook": (
        "push",
        "repository/git_http_url",
        PushEvent.fromGLWebhook
    ),
    "Merge Request Hook": (
        "merge_request",
        "object_attributes/target/http_url",
        MREvent.fromGLWebhook
    ),
    "Note Hook": (
        "note", "merge_request/target/http_url",
        NoteEvent.fromGLWebhook
    ),
}

async def update_project_config(project):
    if not Path(project).is_dir():
        raise _bad_request(f"[{project}] Missing directory")

    try:
        await run_blocking_command(
            ["git", "-C", project, "fetch", "origin", "master:master"])
        inifile = await get_command_output(
            ["git", "-C", project, "show", "master:.abuildd.ini"])
        _CONFIGS[project].read_string(inifile)
    except RuntimeError as e:
        raise _bad_request(f"[{project}] Could not find .abuildd.ini: {e}")

@ROUTES.post(GLOBAL_CONFIG["webhook"]["endpoint"])
async def handle_webhook(request):
    if "X-Gitlab-Event" not in request.headers:
        _bad_request("Missing X-Gitlab-Event header")

    hook = request.headers["X-Gitlab-Event"]
    if hook not in HOOKS:
        _bad_request(f"Unsupported hook type {hook}")

    kind, uri_path, event_class = HOOKS[hook]

    try:
        data = await request.json()
    except json.JSONDecodeError as e:
        _bad_request(f"HTTP payload: {e.msg}")

    object_kind = _assert_exists(data, "object_kind", str)
    if object_kind != kind:
        _bad_request(f"Mismatched types {object_kind} and {kind}")

    uri = _assert_exists(data, uri_path, str)
    if uri not in GLOBAL_CONFIG["projects"]:
        _bad_request(f"Unknown URI '{uri}'")
    project = GLOBAL_CONFIG["projects"][uri]

    if not project in _CONFIGS:
        _CONFIGS[project] = ConfigParser()
        _CONFIGS[project].read_dict(GLOBAL_CONFIG)
    await update_project_config(project)

    if not _CONFIGS[project].getboolean(kind, "enabled"):
        _LOGGER.debug(f"[{project}] Ignoring disabled event of type {kind}")
        return web.Response(text="OK")

    try:
        event = event_class(project, _CONFIGS[project], data, loop)
    except (json.JSONDecodeError, ValueError) as e:
        _bad_request(f"[{project}] HTTP payload: {e.msg}")

    if event:
        async with app["pgpool"].acquire() as db:
            jobs = await event.get_jobs(db, app["mqtt"])

        for arch in jobs:
            job = jobs[arch]
            app["queues"][arch].put_nowait((event._priority, job))  # pylint: disable=protected-access

    return web.Response(text="OK")

def handle_bg_exception(future):
    # TODO: exit if exception raised!
    if future.exception():
        # Raise the suppressed exception
        future.result()

async def start_bg_tasks(app):  # pylint: disable=redefined-outer-name
    app["builders"] = {}
    app["queues"] = {}
    app["queue_watchers"] = []

    for arch in GLOBAL_CONFIG["builders"]["arches"].split("\n"):
        queue, watcher = setup_arch_queue(
            app.loop, app["mqtt"], app["builders"], arch)

        app["queues"][arch] = queue
        app["queue_watchers"].append(watcher)

    app["mqtt_watcher"] = app.loop.create_task(
        mqtt_watch_builders(app["mqtt"], app["builders"]))
    app["mqtt_watcher"].add_done_callback(handle_bg_exception)

async def end_bg_tasks(app):  # pylint: disable=redefined-outer-name
    await app["mqtt"].unsubscribe(["builders/#"])
    await app["mqtt"].disconnect()
    app["mqtt_watcher"].cancel()
    await app["mqtt_watcher"]

    await app["pgpool"].close()

    for watcher in app["queue_watchers"]:
        watcher.cancel()

if __name__ == "__main__":
    # pylint: disable=invalid-name
    logging.getLogger("abuildd").setLevel(GLOBAL_CONFIG["webhook"]["loglevel"])
    logging.basicConfig(format='%(asctime)-15s %(levelname)s %(message)s')

    app = web.Application()
    app.add_routes(ROUTES)
    loop = asyncio.get_event_loop()
    app["pgpool"], app["mqtt"] = loop.run_until_complete(
        conn.init_conns(app.loop))
    app.on_startup.append(start_bg_tasks)
    app.on_cleanup.append(end_bg_tasks)
    web.run_app(app, port=GLOBAL_CONFIG.getint("web", "port"))
