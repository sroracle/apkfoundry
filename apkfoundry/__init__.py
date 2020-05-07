# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019-2020 Max Rees
# See LICENSE for more information.
import collections  # defaultdict
import configparser # ConfigParser
import datetime     # datetime
import enum         # Enum
import logging      # Formatter, getLogger, StreamHandler
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
    "srcdest": "/var/cache/distfiles",
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

class _Colors(enum.Enum):
    NORMAL = "\033[1;0m"
    STRONG = "\033[1;1m"
    CRITICAL = ERROR = RED = "\033[1;31m"
    INFO = GREEN = "\033[1;32m"
    WARNING = YELLOW = "\033[1;33m"
    DEBUG = BLUE = "\033[1;34m"
    MAGENTA = "\033[1;35m"

    def __str__(self):
        return self.value

class _AbuildLogFormatter(logging.Formatter):
    def __init__(self, color=True, sections=False, **kwargs):
        fmt = "%(levelcolor)s%(prettylevel)s%(normal)s%(message)s"
        super().__init__(fmt, **kwargs)

        self.color = color
        self.sections = sections

    def format(self, record):
        if self.color:
            try:
                record.levelcolor = _Colors[record.levelname]
                record.strong = _Colors.STRONG
                record.normal = _Colors.NORMAL
                record.magenta = _Colors.MAGENTA
            except KeyError:
                record.levelcolor = ""
                record.strong = ""
                record.normal = ""
                record.magenta = ""
        else:
            record.levelcolor = ""
            record.strong = ""
            record.normal = ""
            record.magenta = ""

        if self.sections:
            sectionfmt = "section_%s:%s:%s\r\033[0K"
        else:
            # Discard arguments
            sectionfmt = "%.0s%.0s%.0s"

        if record.levelname == "INFO":
            record.prettylevel = ">>> "
        elif record.levelno == 25:
            record.prettylevel = "\t"
        elif record.levelno in (26, 27):
            record.prettylevel = ""
            msg = record.msg
            record.msg = sectionfmt
            if msg.strip():
                record.msg += "\n" if record.levelno == 27 else ""
                record.msg += f"{_Colors.NORMAL}{_Colors.STRONG}>>>"
                record.msg += f" {_Colors.BLUE}{msg}{_Colors.NORMAL}"
        else:
            record.prettylevel = f">>> {record.levelname}: "

        return super().format(record)

def init_logger(name, level="INFO", color=False, sections=False):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    handler = logging.StreamHandler()
    formatter = _AbuildLogFormatter(color=color, sections=sections)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    return logger

def msg2(logger, s, *args, **kwargs):
    if not logger or isinstance(logger, str):
        logger = logging.getLogger(logger)
    if isinstance(s, str):
        logger.log(25, s, *args, **kwargs)
    else:
        for i in s:
            logger.log(25, i, *args, **kwargs)

_SECTIONS = []
def section_start(logger, name, *args, **kwargs):
    if not logger or isinstance(logger, str):
        logger = logging.getLogger(logger)

    ts = str(int(datetime.datetime.now().timestamp()))
    _SECTIONS.append((ts, name))

    logger.log(26, args[0], "start", ts, name, *args[1:], **kwargs)

def section_end(logger, *args, **kwargs):
    if not logger or isinstance(logger, str):
        logger = logging.getLogger(logger)

    if not args:
        args = [""]

    ts, name = _SECTIONS.pop()
    logger.log(27, args[0], "end", ts, name, *args[1:], **kwargs)
