# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import configparser # ConfigParser
import enum         # IntEnum, IntFlag
import errno        # ENXIO
import functools    # partial
import logging      # getLogger
import os           # close, environ, open, O_*, pathsep, write
import queue        # Queue
import shlex        # quote
import subprocess   # check_call, check_output, DEVNULL, Popen
import sys          # stderr, stdout
import threading    # Event
import datetime as dt # timezone
from pathlib import Path

SITE_CONF = Path("/etc/apkfoundry")
SITE_PACKAGE = Path(__file__).parent
LIBEXEC = (SITE_PACKAGE / "libexec").resolve()
if "PATH" in os.environ:
    os.environ["PATH"] = str(LIBEXEC) + os.pathsep + os.environ["PATH"]
else:
    os.environ["PATH"] = str(LIBEXEC)
_HOME = Path("/var/lib/apkfoundry")

_LOGGER = logging.getLogger(__name__)

_ConfigParser = functools.partial(
    configparser.ConfigParser,
    interpolation=None,
    comment_prefixes=(";",),
    delimiters=("=",),
    inline_comment_prefixes=None,
    empty_lines_in_values=True,
    converters={
        "list": lambda s: s.strip().splitlines(),
        "path": Path,
    },
)

_DEFAULT_CONFIG = {
    "DEFAULT": {
        "push": "false",
        "push_branches": "",
        "mr": "false",
        "mr_branches": "",
        "mr_users": "",
        "note": "false",
        "note_users": "",
        "note_keyword": "!build",
    },
    "agent": {
        "name": "agent01",
        "containers": str(_HOME / "containers"),
        "artifacts": str(_HOME / "artifacts"),
        "remote_artifacts": "user@localhost:/var/lib/apkfoundry/artifacts",
        "username": "agent01",
        "password": "password",
        "arches": "apk_arch1\napk_arch2:setarch2",
        "mask": "jobs/#",
        "concurrency": "1",
    },
    "container": {
        "rootid": "1001",
        "subid": "100000",
        "socket": str(_HOME / "root.sock"),
    },
    "database": {
        "filename": str(_HOME / "database.sqlite3"),
    },
    "dispatch": {
        "username": "dispatch",
        "password": "password",
        "events": str(_HOME / "events"),
        "projects": str(_HOME / "projects"),
        "artifacts": str(_HOME / "artifacts"),
        "remotes": "127.0.0.1",
        "keep_events": "false",
    },
    "mqtt": {
        "host": "localhost",
        "port": "1883",
    },
    "web": {
        "base": "https://example.com/cgi-bin/apkfoundry-index.py",
        "css": "/style.css",
        "artifacts": "/artifacts",
        "pretty": "false",
        "limit": "50",
        "debug": "false",
    },
}

@enum.unique
class EType(enum.IntEnum):
    PUSH = 1
    MR = 2
    MANUAL = 4

    def __str__(self):
        return self.name

    def __conform__(self, protocol):
        if protocol is sqlite3.PrepareProtocol:
            return int(self)

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
    IGNORE = DONE | 512    # 520

    def __str__(self):
        return self.name

    def __conform__(self, protocol):
        if protocol is sqlite3.PrepareProtocol:
            return int(self)

    def __str__(self):
        return self.name

def get_config(section=None):
    files = sorted(SITE_CONF.glob("*.ini"))

    config = _ConfigParser()
    config.BOOLEAN_STATES = {"true": True, "false": False}
    config.read_dict(_DEFAULT_CONFIG)
    config.read(files)

    if section:
        return config[section]

    return config

def read_fifo(notifypath):
    with open(notifypath, "r") as notify:
        return notify.read()

def write_fifo(i):
    notifypath = get_config("dispatch").getpath("events") / "notify.fifo"

    if not notifypath.is_fifo():
        raise FileNotFoundError(f"{notifypath} does not exist or isn't a fifo")

    try:
        fd = os.open(notifypath, os.O_WRONLY | os.O_NONBLOCK)
        os.write(fd, i.encode("utf-8"))
        os.close(fd)
        return True
    except OSError as e:
        if e.errno != errno.ENXIO:
            raise
        return False

class IIQueue(queue.Queue):
    def __init__(self, sentinel=None, **kwargs):
        super().__init__(**kwargs)
        self.__sentinel = sentinel or threading.Event()

    def __iter__(self):
        while True:
            yield self.get()

    def put(self, item, **kwargs):
        if self.__sentinel.is_set() and item is not self.__sentinel:
            raise queue.Full

        super().put(item, **kwargs)

        if self.__sentinel.is_set() and item is not self.__sentinel:
            raise queue.Full

    def get(self, **kwargs):
        if self.__sentinel.is_set():
            raise StopIteration

        item = super().get(**kwargs)

        if self.__sentinel.is_set() or item is self.__sentinel:
            raise StopIteration

        return item

_exit_event = threading.Event()

inbound_queue = IIQueue(sentinel=_exit_event)
db_queue = IIQueue(sentinel=_exit_event)
dispatch_queue = IIQueue(sentinel=_exit_event)

agent_queue = IIQueue(sentinel=_exit_event)

def af_exit(recv=False):
    if not _exit_event.is_set():
        if not recv:
            write_fifo("0")

        inbound_queue.put(_exit_event)
        db_queue.put(_exit_event)
        dispatch_queue.put(_exit_event)
        _exit_event.set()

def run(*argv, **kwargs):
    argv = [str(arg) for arg in argv]
    sys.stdout.flush()
    sys.stderr.flush()
    return subprocess.check_call(argv, encoding="utf-8", **kwargs)

def get_output(*argv, **kwargs):
    argv = [str(arg) for arg in argv]
    sys.stdout.flush()
    sys.stderr.flush()
    return subprocess.check_output(argv, encoding="utf-8", **kwargs)

def git_init(dir, clone, *,
        rev="origin/master",
        mrid=None, mrclone=None, mrbranch=None):

    if not (dir / ".git").is_dir():
        run("git", "clone", clone, dir)
        run("git", "worktree", "add", ".apkfoundry", "apkfoundry", cwd=dir)

    run("git", "fetch", "--all", cwd=dir)
    if mrid:
        run("git", "fetch", mrclone, f"{mrbranch}:mr-{mrid}", cwd=dir)

    run("git", "checkout", "--quiet", "--force", rev, cwd=dir)
    run("git", "checkout", "--quiet", "--force", "origin/apkfoundry", cwd=dir / ".apkfoundry")

def dt_timestamp(dto):
    if dto.tzinfo is None:
        ts = dto.replace(tzinfo=dt.timezone.utc)
    else:
        ts = dto

    return dto.timestamp()
