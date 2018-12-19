# SPDX-License-Identifier: MIT
# Copyright (c) 2018 Max Rees
# See LICENSE for more information.
import asyncio # Condition
import json    # dumps
import logging # getLogger, basicConfig
import os      # sched_getaffinity, getloadavg

from hbmqtt.mqtt.constants import QOS_1

from abuildd.config import GLOBAL_CONFIG
from abuildd.utility import assert_exists

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel("DEBUG")
logging.basicConfig(format='%(asctime)-15s %(levelname)s %(message)s')

BUILDERS_STATUSES = (
    "idle",
    "busy",
    "offline",
    "error",
    "failure",
)

COEFF_PROC = GLOBAL_CONFIG.getfloat("builders", "coeff_proc")

class ArchCollection(dict):
    def __init__(self, *args, loop=None, **kwargs):
        self.any_available = asyncio.Condition(loop=loop)
        super().__init__(*args, **kwargs)

def get_avail_builders(builders, arch):
    return [i for i in builders[arch].values() if i.status == "idle"]

async def choose_builder(builders, arch):
    async with builders[arch].any_available:
        avail = get_avail_builders(builders, arch)
        while not avail:
            await builders[arch].any_available.wait()
            avail = get_avail_builders(builders, arch)

        avail.sort(key=lambda x: x._pref, reverse=True)
        builder = avail[0]
        builder.status = "busy"

    return builder.name

class Builder:
    __slots__ = (
        "arch", "name", "status",
        "nprocs", "job", "task",
        "_pref",
    )

    def __init__(self, *, arch, name, status,
                 nprocs=None, job=0, task=0):
        if nprocs is None:
            nprocs = os.sched_getaffinity()
            nprocs = len(nprocs) if nprocs else 0

        self.arch = arch
        self.name = name
        self.status = status
        self.nprocs = nprocs
        self.job = job
        self.task = task

        self._pref = self.calc_pref()

    @staticmethod
    def validate_dict(data):
        assert_exists(data, "arch", str)
        assert_exists(data, "name", str)
        assert_exists(data, "status", str)
        assert_exists(data, "nprocs", int)
        assert_exists(data, "job", int)
        assert_exists(data, "task", int)

        if data["status"] not in BUILDERS_STATUSES:
            raise ValueError("Invalid status")

    @classmethod
    def from_dict(cls, data):
        cls.validate_dict(data)
        return cls(**data)

    def to_dict(self):
        return {slot: getattr(self, slot) for slot in self.__slots__
                if not slot.startswith("_")}

    def will(self):
        status = self.status
        self.status = "offline"

        d = {
            "retain": True,
            "topic": f"builders/{self.arch}/{self.name}",
            "message": json.dumps(self.to_dict()).encode("utf-8"),
            "qos": QOS_1,
        }

        self.status = status
        return d

    async def mqtt_send(self, mqtt):
        dump = json.dumps(self.to_dict()).encode("utf-8")
        await mqtt.publish(
            f"builders/{self.arch}/{self.name}", dump, QOS_1, retain=True)

    def calc_pref(self):
        return int(COEFF_PROC * self.nprocs)
