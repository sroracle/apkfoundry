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

BUILDERS_STATUSES = (
    "idle",
    "busy",
    "offline",
    "error",
    "failure",
)

# c.f. abuildd.sql job_status_enum
JOBS_STATUSES = (
    "new",
    "rejected",
    "building",
    "success",
    "error",
    "failure",
)

JOBS_EVENTS = (
    "push",
    "merge_request",
    "note",
)

async def init_mqtt(uri, topics, loop=None):
    mqtt = MQTTClient(loop=loop)
    try:
        await mqtt.connect(uri)
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
    elif mtype == "tasks":
        res = sanitize_message_tasks(message, topic, data)
    elif mtype == "jobs":
        res = sanitize_message_jobs(message, topic, data)
    else:
        res = None

    return res

def sanitize_message_builders(message, topic, data):
    # builders/<arch>/<name>
    if len(topic) != 3:
        LOGGER.error(f"Invalid builders topic {message.topic}")
        return None

    _ignore, arch, name = topic

    data["name"] = name
    try:
        assert_exists(data, "nprocs", int)
        assert_exists(data, "ram_mb", int)
        assert_exists(data, "status", str)
        assert_exists(data, "job", int)
        assert_exists(data, "task", int)
    except json.JSONDecodeError as e:
        LOGGER.error(f"MQTT {message.topic}: {e.msg}")
        return None

    if data["status"] not in BUILDERS_STATUSES:
        LOGGER.error(f"MQTT {message.topic}: Invalid status {data['status']}")
        return None

    return ("builders", arch, name, data)

def sanitize_message_tasks(message, topic, data):
    # tasks/<arch>/<builder>/<task>
    if len(topic) != 4:
        LOGGER.error(f"Invalid tasks topic {message.topic}")
        return None

    _ignore, arch, builder, task = topic
    try:
        assert_exists(data, "job_id", int)
        assert_exists(data, "status", str)
        assert_exists(data, "shortmsg", str)
        assert_exists(data, "msg", str)
        assert_exists(data, "repo", str)
        assert_exists(data, "package", str)
        assert_exists(data, "version", str)
        assert_exists(data, "maintainer", str)
        # Repeated information from job
        assert_exists(data, "priority", int)
        assert_exists(data, "project", str)
        assert_exists(data, "url", str)
        assert_exists(data, "branch", str)
        assert_exists(data, "commit_id", str)
        assert_exists(data, "mr_id", int)
        assert_exists(data, "event", str)
    except json.JSONDecodeError as e:
        LOGGER.error(f"MQTT {message.topic}: {e.msg}")
        return None

    if data["status"] not in JOBS_STATUSES:
        LOGGER.error(f"MQTT {message.topic}: Invalid status {data['status']}")
        return None

    if data["event"] not in JOBS_EVENTS:
        LOGGER.error(f"MQTT {message.topic}: Invalid event {data['event']}")
        return None

    return ("tasks", arch, builder, task, data)

def sanitize_message_jobs(message, topic, data):
    # jobs/<job>
    if len(topic) != 2:
        LOGGER.error(f"Invalid jobs topic {message.topic}")
        return None

    _ignore, job = topic

    try:
        assert_exists(data, "status", str)
        assert_exists(data, "shortmsg", str)
        assert_exists(data, "msg", str)
        assert_exists(data, "priority", int)
        assert_exists(data, "project", str)
        assert_exists(data, "url", str)
        assert_exists(data, "branch", str)
        assert_exists(data, "commit_id", str)
        assert_exists(data, "mr_id", int)
        assert_exists(data, "event", str)
    except json.JSONDecodeError as e:
        LOGGER.error(f"MQTT {message.topic}: {e.msg}")
        return None

    if data["status"] not in JOBS_STATUSES:
        LOGGER.error(f"MQTT {message.topic}: Invalid status {data['status']}")
        return None

    if data["event"] not in JOBS_EVENTS:
        LOGGER.error(f"MQTT {message.topic}: Invalid event {data['event']}")
        return None

    return ("jobs", job, data)

def create_task(job, package, status="new", shortmsg="", msg=""):
    return {
        "job_id": job.id,
        # Variable information
        "status": status, "shortmsg": shortmsg, "msg": msg,
        # Package information
        "repo": package.repo, "package": package.pkgname,
        "version": f"{package.pkgver}-r{package.pkgrel}",
        "maintainer": package.maintainer[0],
        # Repeated information from job
        "priority": job.priority, "project": job.project, "url": job.url,
        "branch": job.branch, "commit_id": job.commit, "mr_id": job.mr,
        "event": job.event,
    }

def create_job(job, status="new", shortmsg="", msg=""):
    return {
        "status": status, "shortmsg": shortmsg, "msg": msg,
        "priority": job.priority, "project": job.project, "url": job.url,
        "branch": job.branch, "commit_id": job.commit, "mr_id": job.mr,
        "event": job.event,
    }

async def send_task(mqtt, arch, builder, job_id, task_id, task):
    await builder
    builder = builder.result()
    LOGGER.debug(
        f"{task['status']} #{job_id}/{task_id} @ {arch} builder {builder}")

    task = json.dumps(task).encode("utf-8")

    await mqtt.publish(f"tasks/{arch}/{builder}/{task_id}", task, QOS_2)

async def send_job(mqtt, job_id, job):
    LOGGER.debug(f"{job['status']} #{job_id}")

    job = json.dumps(job).encode("utf-8")

    await mqtt.publish(f"jobs/{job_id}", job, QOS_2)
