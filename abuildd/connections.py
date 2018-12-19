# SPDX-License-Identifier: MIT
# Copyright (c) 2018 Max Rees
# See LICENSE for more information.
import logging # getLogger, basicConfig

from asyncpg import create_pool
from hbmqtt.client import MQTTClient, ConnectException
from hbmqtt.mqtt.constants import QOS_1

from abuildd.config import GLOBAL_CONFIG

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel("DEBUG")
logging.basicConfig(format='%(asctime)-15s %(levelname)s %(message)s')

async def init_pgpool(loop=None):
    kwargs = {}
    kwargs["host"] = GLOBAL_CONFIG["database"]["host"] or None
    kwargs["port"] = GLOBAL_CONFIG.getint("database", "port") or None
    kwargs["user"] = GLOBAL_CONFIG["database"]["user"] or None
    kwargs["passfile"] = GLOBAL_CONFIG["database"]["passfile"] or None
    kwargs["database"] = GLOBAL_CONFIG["database"]["name"] or None

    try:
        pgpool = await create_pool(loop=loop, **kwargs)
    except OSError as e:
        LOGGER.error(f"Could not connect to SQL server: {e}")
        exit(10)

    return pgpool

async def init_mqtt(uri, topics, loop=None, config=None):
    mqtt = MQTTClient(loop=loop, config=config)
    try:
        await mqtt.connect(uri)
        await mqtt.subscribe(topics)
    except ConnectException as e:
        LOGGER.error(f"Could not connect to MQTT broker: {e}")
        exit(20)

    return mqtt

async def init_conns(loop=None):
    LOGGER.info("Initializing connections...")

    pgpool = await init_pgpool(loop=loop)
    mqtt = await init_mqtt(
        GLOBAL_CONFIG["enqueue"]["mqtt"], [["builders/#", QOS_1]], loop=loop)

    LOGGER.info("Done!")
    return (pgpool, mqtt)
