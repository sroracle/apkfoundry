# SPDX-License-Identifier: MIT
# Copyright (c) 2018 Max Rees
# See LICENSE for more information.
import asyncio  # CancelledError
import logging  # getLogger
import json     # loads, JSONDecodeError

from abuildd.builders import Builder, get_avail_builders
from abuildd.events import Event
from abuildd.tasks import Job, Task

_LOGGER = logging.getLogger(__name__)

def sanitize_message(message, mtype=None):
    topic = message.topic.split("/")
    res = None

    if not topic:
        return res
    if not mtype:
        mtype = topic[0]
    if mtype != topic[0]:
        return res

    try:
        data = json.loads(message.data)
    except json.JSONDecodeError as e:
        _LOGGER.error(f"JSON decode error on topic {message.topic}: {e}")
        return res

    if mtype == "events":
        res = _sanitize_message_events(message, topic, data)
    elif mtype == "jobs":
        res = _sanitize_message_jobs(message, topic, data)
    elif mtype == "tasks":
        res = _sanitize_message_tasks(message, topic, data)
    elif mtype == "builders":
        res = _sanitize_message_builders(message, topic, data)
    else:
        res = None

    return res

def _sanitize_message_events(message, topic, data):
    # events/<category>/<event_id>
    if len(topic) != 3:
        _LOGGER.error(f"Invalid events topic {message.topic}")
        return None

    _ignore, _category, event_id = topic

    try:
        event_id = int(event_id)
    except ValueError as e:
        _LOGGER.error(f"MQTT {message.topic}: Invalid event {event_id}")
        return None

    try:
        event = Event.from_dict_abs(data)

    except (ValueError, json.JSONDecodeError) as e:
        _LOGGER.error(f"MQTT {message.topic}: {e.msg}")
        return None

    return ("events", event)

def _sanitize_message_jobs(message, topic, data):
    # jobs/<arch>/<builder>/<job_id>
    if len(topic) != 4:
        _LOGGER.error(f"Invalid jobs topic {message.topic}")
        return None

    _ignore, _arch, _builder, job_id = topic

    try:
        job_id = int(job_id)
    except ValueError as e:
        _LOGGER.error(f"MQTT {message.topic}: Invalid job {job_id}")
        return None

    try:
        job = Job.from_dict(data)
    except (ValueError, json.JSONDecodeError) as e:
        _LOGGER.error(f"MQTT {message.topic}: {e.msg}")
        return None

    return ("jobs", job)

def _sanitize_message_tasks(message, topic, data):
    # tasks/<task_id>
    if len(topic) != 2:
        _LOGGER.error(f"Invalid tasks topic {message.topic}")
        return None

    _ignore, task_id = topic
    try:
        task_id = int(task_id)
    except ValueError as e:
        _LOGGER.error(f"MQTT {message.topic}: Invalid task {task_id}")
        return None

    try:
        task = Task.from_dict(data)
    except (ValueError, json.JSONDecodeError) as e:
        _LOGGER.error(f"MQTT {message.topic}: {e.msg}")
        return None

    return ("tasks", task)

def _sanitize_message_builders(message, topic, data):
    # builders/<arch>/<name>
    if len(topic) != 3:
        _LOGGER.error(f"Invalid builders topic {message.topic}")
        return None

    try:
        builder = Builder.from_dict(data)
    except json.JSONDecodeError as e:
        _LOGGER.error(f"MQTT {message.topic}: {e.msg}")
        return None

    return ("builders", builder)

async def mqtt_watch_builders(mqtt, builders):
    while True:
        try:
            message = await mqtt.deliver_message()
            res = sanitize_message(message, "builders")
            if not res:
                continue
            _ignore, builder = res

            arch, name, status = builder.arch, builder.name, builder.status

            if arch not in builders:
                _LOGGER.warning(f"Arch '{arch}' is not enabled")
                continue

            arch_collection = builders[arch]

            if name not in arch_collection:
                _LOGGER.info(f"{arch} builder {name} joined ({status})")

            elif arch_collection[name].status != status:
                _LOGGER.info(f"{arch} builder {name}: {status}")

            async with arch_collection.any_available:
                arch_collection[name] = builder

                if status == "idle":
                    arch_collection.any_available.notify()

                elif not get_avail_builders(builders, arch):
                    _LOGGER.warning(f"No builders available for {arch}")

        except asyncio.CancelledError:
            break
