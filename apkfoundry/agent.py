# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import logging                  # getLogger
import sys                      # exit
from concurrent.futures import ThreadPoolExecutor

import paho.mqtt.client as mqtt
from paho.mqtt.matcher import MQTTMatcher

from . import get_config, agent_queue
frm .build import start_job
from .objects import AFStatus, Job

_LOGGER = logging.getLogger(__name__)

_TOPICS = (
    ("jobs/new/#", 2),
)

class Agent:
    __slots__ = (
        "_mqtt",
        "_host",
        "_port",
        "_mask",

        "name",
        "arches",
        "jobs",
        "jobsdir",
        "workers",
        "containers",
    )

    def __init__(self, cfg, host, port):
        self.name = cfg["name"]
        self.arches = [
            arch.split(":", maxsplit=1) \
            for arch in cfg.getlist("arches")
        ]

        self.jobs = {}

        self._mqtt = mqtt.Client()
        self._mqtt.user_data_set(self)
        self._mqtt.username_pw_set(cfg["username"], cfg["password"])
        self._mqtt.on_connect = self._on_connect
        self._mqtt.on_message = self._on_message

        self._host = host
        self._port = port

        self._mask = MQTTMatcher()
        for topic in cfg.getlist("mask"):
            self._mask[topic] = True

        self.workers = ThreadPoolExecutor(
            max_workers=cfg.getint("concurrency"),
            thread_name_prefix="af-worker-",
        )

        self.containers = cfg.getpath("containers")
        self.jobsdir = cfg.getpath("jobs")

    def loop(self):
        try:
            self._mqtt.connect_async(self._host, self._port)
            self._mqtt.loop_start()

            for obj in agent_queue:
                self._mqtt.publish(str(obj), obj.to_mqtt(), 2)

        except Exception as e:
            _LOGGER.exception("exception:", exc_info=e)

        finally:
            _LOGGER.critical("exiting")
            sys.exit(1)

    def _reject_job(self, job, reason):
        job.status = AFStatus.REJECT
        payload = job.to_mqtt(reason=reason)
        self._mqtt.publish(str(job), payload, 2)

    @staticmethod
    def _on_connect(_client, self, _flags, rc):
        if rc != 0:
            _LOGGER.critical("connection failed: %s", mqtt.connack_string(rc))
            sys.exit(1)

        self._mqtt.subscribe(
            f"jobs/new/+/+/+/+/{self.name}/+/+",
            f"jobs/cancel/+/+/+/+/{self.name}/+/+",
        )

    @staticmethod
    def _on_message(_client, self, msg):
        job = Job.from_mqtt(msg.topic, msg.payload)

        if job.status == AFStatus.CANCEL and job.id in self.jobs:
            # TODO cancel job here
            return

        if job.status == AFStatus.NEW and job.builder == self.name:
            if job.arch not in self.arches:
                self._reject_job(job, "unsupported arch")
                return

            if not any(self._mask.iter_match(msg.topic)):
                self._reject_job(job, "job not whitelisted")
                return

            self.workers.submit(start_job, self, job)

def agent():
    config = get_config()
    mqtt_cfg = config["mqtt"]
    agent_cfg = config["agent"]

    client = Agent(
        agent_cfg,
        mqtt_cfg["host"], mqtt_cfg.getint("port"),
    )
    client.loop()