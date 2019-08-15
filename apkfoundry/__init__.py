# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import configparser # ConfigParser
import functools    # partial
import glob         # glob
import logging      # getLogger
import os           # environ, pathsep
import queue        # Queue
import shlex        # quote
import subprocess   # check_call, check_output, DEVNULL, Popen
import sys          # stderr, stdout
import threading    # Event
from pathlib import Path

SITE_CONF = "/etc/apkfoundry/*.ini"
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
        "jobs": str(_HOME / "jobs"),
        "username": "agent01",
        "password": "password",
        "mask": "jobs/#",
        "concurrency": "1",
    },
    "chroot": {
        "rootid": "1001",
        "subid": "100000",
        "apk": "/sbin/apk.static",
        "bwrap": "/usr/bin/bwrap.nosuid",
        "distfiles": "/var/cache/distfiles",
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
        "remotes": "127.0.0.1",
    },
    "mqtt": {
        "host": "localhost",
        "port": "1883",
    },
    "web": {
        "pretty": "false",
    },
}

def get_config(section=None):
    files = glob.glob(SITE_CONF)
    files.sort()

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
    notifypath = get_config("dispatch").getpath("events")
    notifypath = shlex.quote(str(notifypath / "notify.fifo"))
    i = shlex.quote(i)

    subprocess.Popen(
        f"printf {i} > {notifypath}", shell=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

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
        rev="origin/master", hard=False,
        mrid=None, mrclone=None, mrbranch=None):
    hard = "--hard" if hard else "--keep"

    if not dir.is_dir():
        run("git", "clone", clone, dir)
        run("git", "worktree", "add", ".apkfoundry", "apkfoundry", cwd=dir)

    run("git", "fetch", "--all", cwd=dir)
    if mrid:
        run("git", "fetch", mrclone, f"{mrbranch}:mr-{mrid}", cwd=dir)

    run("git", "reset", hard, rev, cwd=dir)
    run("git", "reset", hard, "origin/apkfoundry", cwd=dir / ".apkfoundry")
