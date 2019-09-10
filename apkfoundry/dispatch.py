# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import json                     # JSONDecodeError
import logging                  # getLogger

import paho.mqtt.client as mqtt

from . import get_config, db_queue, dispatch_queue, af_exit
from .objects import EStatus, Job, Builder, Task

_LOGGER = logging.getLogger(__name__)

# this must be a list to appease paho...
_TOPICS = [
    # Dummy topic that lets the queue-waiting thread notify
    # the mqtt thread of new jobs being available.
    ("_new_job", 1),
    ("builders/#", 1),
    ("jobs/#", 2),
    ("tasks/#", 2),
]

class Dispatcher:
    __slots__ = (
        "_mqtt",
        "_host",
        "_port",

        "builders",
        "jobs",
    )

    def __init__(self, host, port, username, password):
        self._mqtt = mqtt.Client()
        self._mqtt.user_data_set(self)
        self._mqtt.username_pw_set(username, password)
        self._mqtt.on_connect = self._on_connect
        self._mqtt.on_message = self._on_message
        self._mqtt.enable_logger(_LOGGER)

        self._host = host
        self._port = port

        self.builders = {}
        self.jobs = {}

    def loop(self):
        try:
            self._mqtt.connect_async(self._host, self._port)
            self._mqtt.loop_start()

            for job in dispatch_queue:
                if job.arch not in self.jobs:
                    self.jobs[job.arch] = [job]
                else:
                    self.jobs[job.arch].append(job)

                self._mqtt.publish("_new_job", None, 1)

        except Exception as e:
            _LOGGER.exception("exception:", exc_info=e)

        finally:
            _LOGGER.critical("exiting")
            af_exit()

    def _builder_recv(self, msg):
        try:
            builder = Builder.from_mqtt(msg.topic, msg.payload)
        except (json.JSONDecodeError, AssertionError) as e:
            _LOGGER.exception(
                "[%s] invalid payload: '%s'",
                msg.topic, msg.payload, exc_info=e,
            )
            return

        db_queue.put(builder)

        if builder.online:
            _LOGGER.info("builder %s -> online", builder.name)
        else:
            for builders in self.builders.values():
                builders.discard(builder.name)
            _LOGGER.info("builder %s -> offline", builder.name)
            return

        for name, arch in builder.arches.items():
            if name not in self.builders:
                self.builders[name] = set()

            if arch.idle:
                self.builders[name].add(builder.name)
                _LOGGER.info(
                    "builder %s/%s -> idle",
                    builder.name, name,
                )
            else:
                self.builders[name].discard(builder.name)
                _LOGGER.info(
                    "builder %s/%s -> busy",
                    builder.name, name,
                )

    def _task_recv(self, msg):
        try:
            task = Task.from_mqtt(msg.topic, msg.payload)
        except (json.JSONDecodeError, AssertionError) as e:
            _LOGGER.exception(
                "[%s] invalid payload: '%s'",
                msg.topic, msg.payload, exc_info=e,
            )
            return

        db_queue.put(task)
        _LOGGER.info("[%s] %s", str(task), task.status)

    def _job_publish(self, job):
        job.builder = self.builders[job.arch].pop()
        self.builders[job.arch].add(job.builder)

        if not job.id:
            _LOGGER.error("[%s] missing ID before publish", str(job))
            return

        _LOGGER.info("[%s] publish", str(job))
        self._mqtt.publish(str(job), job.to_mqtt(recurse=True), 2)

    def _job_recv(self, msg):
        try:
            job = Job.from_mqtt(msg.topic, msg.payload)
        except (json.JSONDecodeError, AssertionError) as e:
            _LOGGER.exception(
                "[%s] invalid payload: '%s'",
                msg.topic, msg.payload, exc_info=e,
            )
            return 0

        if job.status == EStatus.NEW:
            _LOGGER.debug("[%s] received echo", str(job))
            return job.id

        db_queue.put(job)
        _LOGGER.info("[%s] %s", str(job), job.status)

        try:
            assert job.id == self.jobs[job.arch][0].id, \
                f"current {job.arch} job is {self.jobs[job.arch][0].id}, not {job.id}"
        except (KeyError, IndexError, AssertionError) as e:
            _LOGGER.debug("[%s] ignore (%s)", str(job), e)
            return 0

        if job.status == EStatus.REJECT:
            try:
                self.jobs[job.arch][0].builder = None
            except KeyError:
                _LOGGER.debug("[%s] unknown reject", str(job))

        elif job.status == EStatus.START:
            try:
                del self.jobs[job.arch][0]
            except (KeyError, IndexError):
                _LOGGER.debug("[%s] unknown start", str(job))

        return job.id

    @staticmethod
    def _on_connect(_client, self, _flags, rc):
        if rc != 0:
            _LOGGER.critical("connection failed: %s", mqtt.connack_string(rc))
            af_exit()

        _LOGGER.info("Connected")

        self._mqtt.subscribe(_TOPICS)

    @staticmethod
    def _on_message(_client, self, msg):
        just_touched_job = 0
        if msg.topic.startswith("jobs"):
            just_touched_job = self._job_recv(msg)

        elif msg.topic.startswith("tasks"):
            self._task_recv(msg)

        elif msg.topic.startswith("builders"):
            self._builder_recv(msg)

        for arch in self.jobs:
            if not self.jobs[arch]:
                continue
            if arch not in self.builders:
                continue

            job = self.jobs[arch][0]

            # Avoid immediately re-sending whatever job we were just
            # working on in _job_recv. Although we want to send jobs
            # as often as possible, it is not cool to try to send
            # a job that just got rejected since it is likely that
            # one of the builders will change state on the next
            # message to "busy"
            if job.id == just_touched_job:
                continue

            if not job.builder and self.builders[arch]:
                self._job_publish(job)

def dispatch_thread():
    cfg = get_config()
    mqtt_cfg = cfg["mqtt"]
    dispatch_cfg = cfg["dispatch"]

    client = Dispatcher(
        mqtt_cfg["host"], mqtt_cfg.getint("port"),
        dispatch_cfg["username"], dispatch_cfg["password"],
    )
    client.loop()
