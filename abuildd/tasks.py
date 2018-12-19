# SPDX-License-Identifier: MIT
# Copyright (c) 2018 Max Rees
# See LICENSE for more information.
import asyncio  # Task
import json     # dumps
import logging  # getLogger, basicConfig

from hbmqtt.mqtt.constants import QOS_2
from abuild.file import APKBUILD

from abuildd.utility import assert_exists

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel("DEBUG")
logging.basicConfig(format='%(asctime)-15s %(levelname)s %(message)s')

# c.f. abuildd.sql status_enum
STATUSES = (
    "new",
    "rejected",
    "building",
    "success",
    "error",
    "failure",
)

class Job:
    __slots__ = (
        "id", "event_id",
        "status", "shortmsg", "msg",
        "priority", "arch", "builder", "tasks"
    )

    # pylint: disable=redefined-builtin
    def __init__(self, *, event_id, priority, arch,
                 id=None, status="new", shortmsg="", msg="",
                 builder=None, tasks=None):
        self.id = id
        self.event_id = event_id
        self.status = status
        self.shortmsg = shortmsg
        self.msg = msg
        self.priority = priority
        self.arch = arch
        self.builder = builder
        if tasks:
            self.tasks = tasks
        else:
            self.tasks = []

    async def db_add(self, db):
        job_row = await db.fetchrow(
            """INSERT INTO job(event_id, status, shortmsg, msg,
            priority, arch)
            VALUES($1, $2, $3, $4, $5, $6)
            RETURNING id;""",
            self.event_id, self.status, self.shortmsg, self.msg,
            self.priority, self.arch)

        self.id = job_row["id"]

    def set_status(self, status, shortmsg="", msg=""):
        self.status = status
        self.shortmsg = shortmsg
        self.msg = msg

    async def db_update(self, db, status, shortmsg="", msg=""):
        if not self.id:
            raise RuntimeError("Job hasn't been added yet")

        self.set_status(status, shortmsg, msg)

        await db.fetchrow(
            """UPDATE job
            SET status = $1, shortmsg = $2, msg = $3
            WHERE id = $4""",
            self.status, self.shortmsg, self.msg,
            self.id)

    def add_task(self, task):
        self.tasks.append(task)

    def to_dict(self):
        tasks = []
        for task in self.tasks:
            tasks.append(task.to_dict())

        d = {slot: getattr(self, slot) for slot in self.__slots__}
        d["tasks"] = tasks

        return d

    @staticmethod
    def validate_dict(data):
        assert_exists(data, "id", int)
        assert_exists(data, "event_id", int)
        assert_exists(data, "status", str)
        assert_exists(data, "shortmsg", str)
        assert_exists(data, "msg", str)
        assert_exists(data, "priority", int)
        assert_exists(data, "arch", str)
        assert_exists(data, "builder", str)
        assert_exists(data, "tasks", list)

        if data["status"] not in STATUSES:
            raise ValueError("Invalid status")

        for task in data["tasks"]:
            Task.validate_dict(task)

    @classmethod
    def from_dict(cls, data):
        cls.validate_dict(data)
        return cls(**data)

    async def mqtt_send(self, mqtt):
        if isinstance(self.builder, asyncio.Task):
            await self.builder
            self.builder = self.builder.result()

        LOGGER.info(f"Dispatching job #{self.id} to {self.arch}/{self.builder}")

        dump = json.dumps(self.to_dict()).encode("utf-8")
        await mqtt.publish(
            f"jobs/{self.arch}/{self.builder}/{self.id}", dump, QOS_2)

class Task:
    __slots__ = (
        "id", "job_id",
        "status", "shortmsg", "msg",
        "repo", "package", "version", "maintainer"
    )

    # pylint: disable=redefined-builtin
    def __init__(self, *, job_id, repo, package, version, maintainer,
                 id=None, status="new", shortmsg="", msg=""):
        self.id = id
        self.job_id = job_id
        self.status = status
        self.shortmsg = shortmsg
        self.msg = msg
        self.repo = repo
        self.package = package
        self.version = version
        self.maintainer = maintainer

    async def db_add(self, db):
        task_row = await db.fetchrow(
            """INSERT INTO task(job_id, package, version, maintainer)
            VALUES($1, $2, $3, $4)
            RETURNING id;""",
            self.job_id, self.package, self.version, self.maintainer)

        self.id = task_row["id"]

    def set_status(self, status, shortmsg="", msg=""):
        self.status = status
        self.shortmsg = shortmsg
        self.msg = msg

    async def db_update(self, db, status, shortmsg="", msg=""):
        if not self.id:
            raise RuntimeError("Task hasn't been added yet")

        self.set_status(status, shortmsg, msg)

        await db.fetchrow(
            """UPDATE task
            SET status = $1, shortmsg = $2, msg = $3
            WHERE id = $4""",
            self.status, self.shortmsg, self.msg,
            self.id)

    def to_dict(self):
        return {slot: getattr(self, slot) for slot in self.__slots__}

    @classmethod
    def from_APKBUILD(cls, job_id, pkg):
        if not isinstance(pkg, APKBUILD):
            raise ValueError("pkg must be of type APKBUILD")

        return cls(
            job_id=job_id, repo=pkg.repo, package=pkg.pkgname,
            version=pkg.pkgver, maintainer=pkg.maintainer[0])

    @staticmethod
    def validate_dict(data):
        assert_exists(data, "id", int)
        assert_exists(data, "job_id", int)
        assert_exists(data, "status", str)
        assert_exists(data, "shortmsg", str)
        assert_exists(data, "msg", str)
        assert_exists(data, "repo", str)
        assert_exists(data, "package", str)
        assert_exists(data, "version", str)
        assert_exists(data, "maintainer", str)

        if data["status"] not in STATUSES:
            raise ValueError("Invalid status")

    @classmethod
    def from_dict(cls, data):
        cls.validate_dict(data)
        return cls(**data)

    async def mqtt_send(self, mqtt):
        dump = json.dumps(self.to_dict()).encode("utf-8")
        await mqtt.publish(f"tasks/{self.id}", dump, QOS_2)
