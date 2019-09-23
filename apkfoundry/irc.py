# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2018-2019 Max Rees
# See LICENSE for more information.
import logging # getLogger
import sys     # exit

import paho.mqtt.client as mqtt
from paho.mqtt.matcher import MQTTMatcher
from PyIRC.io.socket import IRCSocket
from PyIRC.extensions import ircv3_recommended
from PyIRC.formatting.formatters import FormattingCodes

from apkfoundry import get_config
from apkfoundry.objects import Event, Job, Task

_LOGGER = logging.getLogger(__name__)

_CFG = get_config()
_IRC_CFG = _CFG["irc"]
_MQTT_CFG = _CFG["mqtt"]

_WEB_CFG = _CFG["web"]
_WEB_BASE = _WEB_CFG["base"]
_WEB_PRETTY =_WEB_CFG.getboolean("pretty")

if _WEB_PRETTY:
    _URL_SEPS = ("/", "/")
else:
    _URL_SEPS = ("?", "=")

_TOPICS = [
    ("jobs/#", 2),
    ("tasks/#", 2),
]

def link(page, iid):
    return "".join((
        _WEB_BASE,
        _URL_SEPS[0],
        page,
        _URL_SEPS[1],
        str(iid),
    ))

class AFIRCProtocol(IRCSocket):
    def __init__(self):
        self.hooks = {
            "jobs/": self.announce_job,
            "tasks/": self.announce_task,
        }

        if _IRC_CFG.getboolean("colors"):
            self.bold = FormattingCodes.bold
            self.reset = FormattingCodes.normal
        else:
            self.bold = ""
            self.reset = ""

        chans = [i for i in _IRC_CFG if i.startswith("#")]
        self.mask = MQTTMatcher()
        for chan in chans:
            topics = set(_IRC_CFG.getlist(chan))
            for topic in topics:
                try:
                    self.mask[topic].add(chan)
                except KeyError:
                    self.mask[topic] = set()
                    self.mask[topic].add(chan)

        super().__init__(**{
            "serverport": (
                _IRC_CFG["host"], _IRC_CFG.getint("port")
            ),
            "ssl": _IRC_CFG.getboolean("ssl"),
            "nick": _IRC_CFG["nick"],
            "username": _IRC_CFG["username"],
            "gecos": _IRC_CFG["gecos"],
            "extensions": ircv3_recommended,
            "join": chans,
        })

    def mqtt_init(self):
        self._mqtt = mqtt.Client()
        self._mqtt.user_data_set(self)
        self._mqtt.on_connect = self._mqtt_connect
        self._mqtt.on_message = self._mqtt_message
        self._mqtt.enable_logger(_LOGGER)
        self._mqtt.connect_async(_MQTT_CFG["host"], _MQTT_CFG.getint("port"))
        self._mqtt.loop_start()

    @staticmethod
    def _mqtt_connect(_client, self, _flags, rc):
        if rc != 0:
            _LOGGER.critical("connection failed: %s", mqtt.connack_string(rc))
            try:
                self.send("QUIT", ["Failed to connect to MQTT broker"])
            except:
                pass
            sys.exit(1)

        _LOGGER.info("Connected to MQTT broker")
        self._mqtt.subscribe(_TOPICS)

    @staticmethod
    def _mqtt_message(_client, self, msg):
        for topic_prefix, hook in self.hooks.items():
            if msg.topic.startswith(topic_prefix):
                announcement = hook(msg.topic, msg.payload)
                break
        else:
            _LOGGER.debug("Unhandled MQTT topic %s", msg.topic)
            return

        for chans in self.mask.iter_match(msg.topic):
            for chan in chans:
                self.send("PRIVMSG", [chan, announcement])

    def announce_job(self, topic, payload):
        try:
            job = Job.from_mqtt(topic, payload)
        except Exception as e:
            _LOGGER.error("Invalid job %s: %s", topic, e)
            return

        if not isinstance(job.event, int):
            job.event = job.event.id

        msg = [
            f"[Event #{job.event}] {self.bold}Job #{job.id}:{self.reset}",
            f"{job.status!s}:",
            f"{job.builder}/{job.arch} with {len(job.tasks)} tasks",
            link("jobs", job.id),
        ]

        return " ".join(msg)

    def announce_task(self, topic, payload):
        try:
            task = Task.from_mqtt(topic, payload)
        except Exception as e:
            _LOGGER.error("Invalid task %s: %s", topic, e)
            return

        if not isinstance(task.job, int):
            task.job = task.job.id

        msg = [
            f"[Job #{task.job}] {self.bold}Task #{task.id}:{self.reset}",
            f"{task.status!s}:",
            f"{task.repo}/{task.pkg}",
            link("tasks", task.id),
        ]

        if task.tail:
            msg += ["-", task.tail]

        return " ".join(msg)
