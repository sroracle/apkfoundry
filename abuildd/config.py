# SPDX-License-Identifier: MIT
# Copyright (c) 2018 Max Rees
# See LICENSE for more information.
from glob import glob
import configparser

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
}

_files = glob(SITE_CONF)  # pylint: disable=invalid-name
_files.sort()

CONFIGS = {}
CONFIGS["global"] = configparser.ConfigParser(
    interpolation=None, comment_prefixes=(";",))
CONFIGS["global"].read_dict(DEFAULT_CONFIG)
CONFIGS["global"].read(_files)
GLOBAL_CONFIG = CONFIGS["global"]
