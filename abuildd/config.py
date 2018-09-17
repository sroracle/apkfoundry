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
    "builders": {
        "arches": "x86_64\npmmx\nppc\nppc64\naarch64",
        "coeff_proc": 1,
        "coeff_ram": "0.001",
    },
}

_files = glob(SITE_CONF)
_files.sort()

CONFIGS = {}
CONFIGS["global"] = configparser.ConfigParser(interpolation=None)
CONFIGS["global"].read_dict(DEFAULT_CONFIG)
CONFIGS["global"].read(_files)
GLOBAL_CONFIG = CONFIGS["global"]
