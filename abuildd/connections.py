import logging  # getLogger, basicConfig
import sys      # exit

import asyncpg  # create_pool
from hbmqtt.client import MQTTClient, ConnectException

from abuildd.config import GLOBAL_CONFIG

logger = logging.getLogger(__name__)
logger.setLevel("DEBUG")
logging.basicConfig(format='%(asctime)-15s %(levelname)s %(message)s')

async def init_pgpool(loop=None):
    kwargs = {}
    kwargs["host"] = GLOBAL_CONFIG["database"]["host"] or None
    kwargs["port"] = GLOBAL_CONFIG.getint("database", "port") or None
    kwargs["user"] = GLOBAL_CONFIG["database"]["user"] or None
    kwargs["passfile"] = GLOBAL_CONFIG["database"]["passfile"] or None
    kwargs["database"] = GLOBAL_CONFIG["database"]["name"] or None

    try:
        pgpool = await asyncpg.create_pool(loop=loop, **kwargs)
    except OSError as e:
        logger.error(f"Could not connect to SQL server: {e}")
        sys.exit(10)

    return pgpool

async def init_mqtt(topics, loop=None):
    mqtt = MQTTClient(loop=loop)
    try:
        await mqtt.connect(GLOBAL_CONFIG["mqtt"]["uri"])
        await mqtt.subscribe(topics)
    except ConnectException as e:
        logger.error(f"Could not connect to MQTT broker: {e}")
        sys.exit(20)

    return mqtt
