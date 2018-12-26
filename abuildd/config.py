# SPDX-License-Identifier: MIT
# Copyright (c) 2018 Max Rees
# See LICENSE for more information.
import configparser      # ConfigParser
import functools         # partial
from glob import glob

SITE_CONF = "/etc/abuildd/*.ini"
DEFAULT_CONFIG = {
    "web": {
        "port": "8080",
    },
    "database": {
        "host": "",
        "port": 5432,
        "user": "postgres",
        "passfile": "~/.pgpass",
        "name": "abuildd",
    },
    "push": {
        "enabled": "True",
        "priority": "500",
        "allowed_users": "",
        "denied_users": "",
        "branches": "master",
    },
    "merge_request": {
        "enabled": "True",
        "priority": "500",
        "allowed_users": "",
        "denied_users": "",
    },
    "note": {
        "enabled": "True",
        "priority": "500",
        "users": "",
        "allowed_users": "",
        "denied_users": "",
        "keyword": "[build please]",
    },
    "webhook": {
        "loglevel": "DEBUG",
        "endpoint": "/abuildd/webhook",
    },
    "enqueue": {
        "mqtt": "mqtt://enqueue@localhost/",
    },
    "agent": {
        "mqtt": "mqtt://arch_name@localhost/",
        "arch": "ppc64",
        "name": "builder-ppc64",
    },
    "irc": {
        "mqtt": "mqtt://irc@localhost/",
        "server": "irc.example.com",
        "port": "6667",
        "ssl": "False",
        "nick": "buildbot",
        "username": "abuildd-irc",
        "gecos": "abuildd-irc bot",
        "colors": "False",
        "builders_chans": "#abuildd",
        "builders_statuses": "offline",
        "events_chans": "#abuildd",
        "events_statuses": "new\nrejected",
        "jobs_chans": "#abuildd",
        "jobs_statuses": "new",
        "tasks_chans": "#abuildd",
        "tasks_statuses": "building\nsuccess\nerror\nfailure",
        "cmd_chans": "#abuildd",
    },
    "builders": {
        "arches": "x86_64\npmmx\nppc\nppc64\naarch64",
        "coeff_proc": 1,
    },
    "projects": {},
}

DEFAULT_PRIORITY = 500

def _list(value):
    return value.split("\n")

def _priorityspec(value):
    value = value.split("\n")
    d = {}

    if not value or value == [""]:
        return d

    for entry in value:
        entry = entry.split(":", maxsplit=1)
        if len(entry) == 1:
            d[entry[0]] = DEFAULT_PRIORITY
        else:
            d[entry[0]] = int(entry[1])

    return d

_files = glob(SITE_CONF)  # pylint: disable=invalid-name
_files.sort()

ConfigParser = functools.partial(
    configparser.ConfigParser,
    interpolation=None,
    comment_prefixes=(";",),
    delimiters=("=",),
    converters={
        "priorities": _priorityspec,
        "list": _list,
    },
)

GLOBAL_CONFIG = ConfigParser()
GLOBAL_CONFIG.read_dict(DEFAULT_CONFIG)
GLOBAL_CONFIG.read(_files)
