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
    "mqtt": {
        "uri": "mqtt://localhost",
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
    "irc": {
        "server": "irc.example.com",
        "port": "6667",
        "ssl": "False",
        "nick": "buildbot",
        "username": "abuildd-irc",
        "gecos": "abuildd-irc bot",
        "colors": "False",
        "builders_chans": "#abuildd",
        "builders_statuses": "offline",
        "jobs_chans": "#abuildd",
        "jobs_statuses": "rejected",
        "tasks_chans": "#abuildd",
        "tasks_statuses": "new\nrejected\nbuilding\nsuccess\nerror\nfailure",
        "cmd_chans": "#abuildd",
    },
    "builders": {
        "arches": "x86_64\npmmx\nppc\nppc64\naarch64",
        "coeff_proc": 1,
        "coeff_ram": "0.001",
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
