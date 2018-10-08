# SPDX-License-Identifier: MIT
# Copyright (c) 2018 Max Rees
# See LICENSE for more information.
import logging  # getLogger
import sys      # exit
import json     # loads, JSONDecodeError

from hbmqtt.client import MQTTClient, ConnectException
from hbmqtt.mqtt.constants import QOS_2

from abuildd.config import GLOBAL_CONFIG
from abuildd.utility import assert_exists

LOGGER = logging.getLogger(__name__)

async def init_mqtt(topics, loop=None):
    mqtt = MQTTClient(loop=loop)
    try:
        await mqtt.connect(GLOBAL_CONFIG["mqtt"]["uri"])
        await mqtt.subscribe(topics)
    except ConnectException as e:
        LOGGER.error(f"Could not connect to MQTT broker: {e}")
        sys.exit(20)

    return mqtt

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

    if mtype == "builders":
        res = sanitize_message_builders(message, topic, data)
    else:
        res = None

    return res

def sanitize_message_builders(message, topic, data):
    # builders/<arch>/<name>
    if len(topic) != 3:
        LOGGER.error(f"Invalid builders topic {message.topic}")

    arch = topic[1]
    name = topic[2]

    data["name"] = name

    try:
        assert_exists(data, "nprocs", int)
        assert_exists(data, "ram_mb", int)
        assert_exists(data, "status", str)
    except json.JSONDecodeError as e:
        LOGGER.error(f"MQTT {message.topic}: {e.msg}")
        return None

    if data["status"] not in ("idle", "busy", "offline"):
        LOGGER.error(f"MQTT {message.topic}: Invalid status {data['status']}")
        return None

    return ("builders", arch, name, data)

async def mqtt_send_task(mqtt, builder, arch, job_id, task_id, task):
    await builder
    builder = builder.result()
    LOGGER.debug(f"Sending #{job_id}/{task_id} to {arch} builder {builder}")
    await mqtt.publish(f"tasks/{arch}/{builder}/{task_id}", task, QOS_2)
