# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import functools                # partial
import logging                  # getLogger
import sys                      # exit
from concurrent.futures import ThreadPoolExecutor

import paho.mqtt.client as mqtt
from paho.mqtt.matcher import MQTTMatcher

from . import get_config, agent_queue
from .build import run_job
from .objects import EStatus, Job, BStatus, Builder

_LOGGER = logging.getLogger(__name__)

class Agent:
    __slots__ = (
        "_mqtt",
        "_host",
        "_port",
        "_mask",
        "_will",

        "setarch",
        "builder",
        "jobs",
        "jobsdir",
        "workers",
        "containers",
    )

    def __init__(self, cfg, host, port):
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

        self.setarch = [
            arch.split(":", maxsplit=1) \
            for arch in cfg.getlist("arches")
        ]
        self.setarch = {
            arch[0]: arch[1] if len(arch) > 1 else None \
            for arch in self.setarch
        }

        self.builder = Builder(
            name=cfg["name"],
            arches={arch: BStatus.AVAILABLE for arch in self.setarch},
        )
        self._will = Builder(
            name=cfg["name"],
            arches={arch: BStatus.OFFLINE for arch in self.setarch},
        )

        self.jobs = {}
        self.jobsdir = cfg.getpath("jobs")

        self.workers = ThreadPoolExecutor(
            max_workers=cfg.getint("concurrency"),
            thread_name_prefix="af-worker-",
        )

        self.containers = cfg.getpath("containers")

    def loop(self):
        try:
            self._mqtt.connect_async(self._host, self._port)
            self._mqtt.loop_start()

            self.publish_builder()

            for obj in agent_queue:
                self._mqtt.publish(str(obj), obj.to_mqtt(), 2)

        except Exception as e:
            _LOGGER.exception("exception:", exc_info=e)

        finally:
            try:
                self.builder = self._will
                self.publish_builder()
            except:
                _LOGGER.warning("Could not mark self as offline!")

            _LOGGER.critical("exiting")
            sys.exit(1)

    def publish_builder(self):
        self._mqtt.publish(
            str(self.builder), self.builder.to_mqtt(), 1,
            retain=True,
        )

    def _job_done(self, job, future):
        exc = future.exception()
        if exc:
            _LOGGER.exception("[%s]", job, exc_info=exc)
        else:
            _LOGGER.info("[%s] done", job)

    def _reject_job(self, job, reason):
        _LOGGER.warning("[%s] reject: %s", job, reason)
        job.status = EStatus.REJECT
        job.payload = reason
        self._mqtt.publish(str(job), job.to_mqtt(), 2)

    @staticmethod
    def _on_connect(_client, self, _flags, rc):
        if rc != 0:
            _LOGGER.critical("connection failed: %s", mqtt.connack_string(rc))
            sys.exit(1)

        _LOGGER.info("Connected")

        self._mqtt.will_set(
            str(self._will), self._will.to_mqtt(), 1,
            retain=True,
        )

        self._mqtt.subscribe([
            (f"jobs/NEW/+/+/+/+/{self.builder.name}/+/+", 2),
            (f"jobs/CANCEL/+/+/+/+/{self.builder.name}/+/+", 2),
        ])

    @staticmethod
    def _on_message(_client, self, msg):
        job = Job.from_mqtt(msg.topic, msg.payload)

        if job.status == EStatus.CANCEL and job.id in self.jobs:
            # TODO cancel job here
            return

        if job.status == EStatus.NEW and job.builder == self.builder.name:
            if job.arch not in self.builder.arches:
                self._reject_job(job, "unsupported arch")
                return

            if self.builder.arches[job.arch] != BStatus.AVAILABLE:
                self._reject_job(job, "arch is unavailable")
                return

            if not any(self._mask.iter_match(msg.topic)):
                self._reject_job(job, "job not whitelisted")
                return

            _LOGGER.info("[%s] starting", job)
            future = self.workers.submit(run_job, self, job)
            future.add_done_callback(
                functools.partial(self._job_done, job),
            )

def agent():
    config = get_config()
    mqtt_cfg = config["mqtt"]
    agent_cfg = config["agent"]

    client = Agent(
        agent_cfg,
        mqtt_cfg["host"], mqtt_cfg.getint("port"),
    )
    client.loop()
