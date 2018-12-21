# SPDX-License-Identifier: MIT
# Copyright (c) 2018 Max Rees
# See LICENSE for more information.
import asyncio  # CancelledError
import logging  # getLogger
import json     # loads, JSONDecodeError

from abuildd.builders import Builder, get_avail_builders
from abuildd.events import PushEvent, MREvent, NoteEvent
from abuildd.tasks import Job, Task
from abuildd.utility import assert_exists

LOGGER = logging.getLogger(__name__)

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
        LOGGER.error(f"JSON decode error on topic {message.topic}: {e}")
        return res

    if mtype == "events":
        res = sanitize_message_events(message, topic, data)
    elif mtype == "jobs":
        res = sanitize_message_jobs(message, topic, data)
    elif mtype == "tasks":
        res = sanitize_message_tasks(message, topic, data)
    elif mtype == "builders":
        res = sanitize_message_builders(message, topic, data)
    else:
        res = None

    return res

def sanitize_message_events(message, topic, data):
    # events/<category>/<event_id>
    if len(topic) != 3:
        LOGGER.error(f"Invalid events topic {message.topic}")
        return None

    _ignore, _category, event_id = topic

    try:
        event_id = int(event_id)
    except ValueError as e:
        LOGGER.error(f"MQTT {message.topic}: Invalid event {event_id}")
        return None

    try:
        category = assert_exists(data, "category", str)
        if category == "push":
            event = PushEvent.from_dict(data)
        elif category == "merge_request":
            event = MREvent.from_dict(data)
        elif category == "note":
            event = NoteEvent.from_dict(data)
        else:
            raise ValueError(f"Invalid category {category}")

    except (ValueError, json.JSONDecodeError) as e:
        LOGGER.error(f"MQTT {message.topic}: {e.msg}")
        return None

    return ("events", event)

def sanitize_message_jobs(message, topic, data):
    # jobs/<arch>/<builder>/<job_id>
    if len(topic) != 4:
        LOGGER.error(f"Invalid jobs topic {message.topic}")
        return None

    _ignore, _arch, _builder, job_id = topic

    try:
        job_id = int(job_id)
    except ValueError as e:
        LOGGER.error(f"MQTT {message.topic}: Invalid job {job_id}")
        return None

    try:
        job = Job.from_dict(data)
    except (ValueError, json.JSONDecodeError) as e:
        LOGGER.error(f"MQTT {message.topic}: {e.msg}")
        return None

    return ("jobs", job)

def sanitize_message_tasks(message, topic, data):
    # tasks/<task_id>
    if len(topic) != 2:
        LOGGER.error(f"Invalid tasks topic {message.topic}")
        return None

    _ignore, task_id = topic
    try:
        task_id = int(task_id)
    except ValueError as e:
        LOGGER.error(f"MQTT {message.topic}: Invalid task {task_id}")
        return None

    try:
        task = Task.from_dict(data)
    except (ValueError, json.JSONDecodeError) as e:
        LOGGER.error(f"MQTT {message.topic}: {e.msg}")
        return None

    return ("tasks", task)

def sanitize_message_builders(message, topic, data):
    # builders/<arch>/<name>
    if len(topic) != 3:
        LOGGER.error(f"Invalid builders topic {message.topic}")
        return None

    try:
        builder = Builder.from_dict(data)
    except json.JSONDecodeError as e:
        LOGGER.error(f"MQTT {message.topic}: {e.msg}")
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
                LOGGER.error(f"Arch '{arch}' is not enabled")
                continue

            arch_collection = builders[arch]

            if name not in arch_collection:
                LOGGER.info(f"{arch} builder {name} joined ({status})")

            elif arch_collection[name].status != status:
                LOGGER.info(f"{arch} builder {name}: {status}")

            async with arch_collection.any_available:
                arch_collection[name] = builder

                if status == "idle":
                    arch_collection.any_available.notify()

                elif not get_avail_builders(builders, arch):
                    LOGGER.warning(f"No builders available for {arch}")

        except asyncio.CancelledError:
            break
