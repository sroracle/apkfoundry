# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019-2020 Max Rees
# See LICENSE for more information.
import collections  # defaultdict
import configparser # ConfigParser
import datetime     # datetime
import enum         # Enum, IntFlag, unique
import functools    # partial
import logging      # Formatter, getLogger, StreamHandler
import os           # environ, pathsep
import pwd          # getpwuid
import subprocess   # check_call
import sys          # stderr, stdout
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

class Colors(enum.Enum):
    NORMAL = "\033[1;0m"
    STRONG = "\033[1;1m"
    CRITICAL = ERROR = RED = "\033[1;31m"
    INFO = GREEN = "\033[1;32m"
    WARNING = YELLOW = "\033[1;33m"
    DEBUG = BLUE = "\033[1;34m"
    MAGENTA = "\033[1;35m"

    def __str__(self):
        return self.value

@enum.unique
class EStatus(enum.IntFlag):
    NEW = 1
    REJECT = 2
    START = 4
    DONE = 8
    ERROR = DONE | 16      # 24
    CANCEL = ERROR | 32    # 56
    SUCCESS = DONE | 64    # 72
    FAIL = ERROR | 128     # 152
    DEPFAIL = CANCEL | 256 # 312
    SKIP = DONE | 512      # 520

    def __str__(self):
        return self.name

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

def rootid():
    return pwd.getpwnam("af-root")

def check_call(args, **kwargs):
    args = [str(arg) for arg in args]
    sys.stdout.flush()
    sys.stderr.flush()
    return subprocess.check_call(args, **kwargs)

def get_branch(gitdir=None):
    args = ["git"]
    if gitdir:
        args += ["-C", str(gitdir)]
    args += ["branch", "--show-current"]
    return subprocess.check_output(args, encoding="utf-8").strip()

def get_branchdir(gitdir=None, branch=None):
    if not branch:
        branch = get_branch(gitdir)
    if not gitdir:
        gitdir = Path.cwd()
    branch = branch.replace("/", ":")
    for i in (branch, "master"):
        path = gitdir / ".apkfoundry" / i
        if path.exists():
            return path

    raise FileNotFoundError(
        "could not find .apkfoundry/{branch} or .apkfoundry/master"
    )

def get_arch():
    return subprocess.check_output(
        [APK_STATIC, "--print-arch"],
        encoding="utf-8",
    ).strip()

class abuildLogFormatter(logging.Formatter):
    def __init__(self, color=True, sections=False, **kwargs):
        fmt = "%(levelcolor)s%(prettylevel)s%(normal)s%(message)s"
        super().__init__(fmt, **kwargs)

        self.color = color
        self.sections = sections

    def format(self, record):
        if self.color:
            try:
                record.levelcolor = Colors[record.levelname]
                record.strong = Colors.STRONG
                record.normal = Colors.NORMAL
                record.magenta = Colors.MAGENTA
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
                record.msg += f"{Colors.NORMAL}{Colors.STRONG}>>>"
                record.msg += f" {Colors.BLUE}{msg}{Colors.NORMAL}"
        else:
            record.prettylevel = f">>> {record.levelname}: "

        return super().format(record)

def init_logger(name, level="INFO", color=False, sections=False):
    logger = logging.getLogger(name)
    logger.setLevel(level)
    handler = logging.StreamHandler()
    formatter = abuildLogFormatter(color=color, sections=sections)
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

_sections = []
def section_start(logger, name, *args, **kwargs):
    if not logger or isinstance(logger, str):
        logger = logging.getLogger(logger)

    ts = str(int(datetime.datetime.now().timestamp()))
    _sections.append((ts, name))

    logger.log(26, args[0], "start", ts, name, *args[1:], **kwargs)

def section_end(logger, *args, **kwargs):
    if not logger or isinstance(logger, str):
        logger = logging.getLogger(logger)

    if not args:
        args = [""]

    ts, name = _sections.pop()
    logger.log(27, args[0], "end", ts, name, *args[1:], **kwargs)
