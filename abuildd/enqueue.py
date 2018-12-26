# SPDX-License-Identifier: MIT
# Copyright (c) 2018 Max Rees
# See LICENSE for more information.
import asyncio      # PriorityQueue
import functools    # partial
import logging      # getLogger
from abuildd.builders import ArchCollection, choose_builder

LOGGER = logging.getLogger(__name__)

def setup_arch_queue(loop, mqtt, all_builders, arch):
    queue = asyncio.PriorityQueue(loop=loop)
    all_builders[arch] = ArchCollection(loop=loop)

    watcher = loop.create_task(watch_queue(mqtt, queue, all_builders, arch))
    watcher.add_done_callback(functools.partial(stop_queue, queue))

    return (queue, watcher)

async def watch_queue(mqtt, queue, builders, arch):
    while True:
        builder = await choose_builder(builders, arch)
        _priority, job = await queue.get()
        queue.task_done()
        await job.mqtt_send(mqtt, builder)

def stop_queue(queue, watcher):
    if watcher.cancelled():
        while not queue.empty():
            _priority, job = queue.get_nowait()
            queue.task_done()
            LOGGER.error(f"Job #{job.id} not dispatched")

    elif watcher.exception():
        watcher.result()
