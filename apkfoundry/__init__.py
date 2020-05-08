# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019-2020 Max Rees
# See LICENSE for more information.
import collections  # defaultdict
import configparser # ConfigParser
import logging      # getLogger
import os           # environ, pathsep
from pathlib import Path

SYSCONFDIR = Path("/etc/apkfoundry")
LIBEXECDIR = Path(__file__).parent.parent / "libexec"
if not LIBEXECDIR.is_dir():
    LIBEXECDIR = Path("/usr/libexec/apkfoundry")
LOCALSTATEDIR = Path("/var/lib/apkfoundry")
APK_STATIC = SYSCONFDIR / "skel:bootstrap/apk.static"

if "PATH" in os.environ:
    os.environ["PATH"] = str(LIBEXECDIR) + os.pathsep + os.environ["PATH"]
else:
    os.environ["PATH"] = str(LIBEXECDIR)

MOUNTS = {
    "aportsdir": "/af/aports",
    "builddir": "/af/build",
    "repodest": "/af/repos",
    "srcdest": "/af/distfiles",
}

_LOGGER = logging.getLogger(__name__)

def _config_map(s):
    d = {}
    for i in s.strip().splitlines():
        i = i.strip().split(maxsplit=1)
        d[i[0]] = i[1]
    return d

def _config_maplist(s):
    d = collections.defaultdict(list)
    for i in s.strip().splitlines():
        i = i.strip().split()
        d[i[0]].extend(i[1:])
    return d

def _ConfigParser(**kwargs):
    parser = configparser.ConfigParser(
        interpolation=None,
        comment_prefixes=(";",),
        delimiters=("=",),
        inline_comment_prefixes=None,
        empty_lines_in_values=True,
        converters={
            "list": lambda s: s.strip().splitlines(),
            "path": Path,
            "map": _config_map,
            "maplist": _config_maplist,
        },
        **kwargs,
    )
    parser.BOOLEAN_STATES = {"true": True, "false": False}
    return parser

_DEFAULT_SITE_CONFIG = {
    "container": {
        "subid": "100000",
    },
    "setarch": {
    },
}

_DEFAULT_LOCAL_CONFIG = {
    "master": {
        # Required
        "repos": "",
        "bootstrap_repo": "",
        # Optional
        "deps_ignore": "",
        "deps_map": "",
        "on_failure": "stop",
        "skip": "",
    },
}

def site_conf(section=None):
    files = sorted(SYSCONFDIR.glob("*.ini"))

    config = _ConfigParser()
    config.read_dict(_DEFAULT_SITE_CONFIG)
    config.read(files)

    if section:
        return config[section]

    return config

def local_conf(gitdir=None, section=None):
    if gitdir is None:
        gitdir = Path.cwd()
    files = sorted((Path(gitdir) / ".apkfoundry").glob("*.ini"))

    config = _ConfigParser(default_section="master")
    config.read_dict(_DEFAULT_LOCAL_CONFIG)
    config.read(files)

    if section:
        if section not in config:
            config.add_section(section)
        return config[section]

    return config
