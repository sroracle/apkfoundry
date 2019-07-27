# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import argparse     # action, ArgumentParser
import enum         # Flag
import logging      # getLogger
import os           # pipe, unlink
import selectors    # DefaultSelector
import shlex        # split
import socket       # CMSG_SPACE, SCM_RIGHTS, SOL_SOCKET
import socketserver # StreamRequestHandler, UnixStreamServer
import struct       # calcsize, pack, Struct
import sys          # exc_info
from pathlib import Path

from . import get_config
from .chroot import chroot, chroot_bootstrap, chroot_init

_LOGGER = logging.getLogger(__name__)
_CFG = get_config("chroot")
_SOCK_PATH = _CFG.getpath("socket")
_NUM_FDS = 4
_PASSFD_FMT = _NUM_FDS * "i"
_PASSFD_SIZE = socket.CMSG_SPACE(struct.calcsize(_PASSFD_FMT))
_BUF_SIZE = 4096

class _ParseOrRaise(argparse.ArgumentParser):
    class Error(Exception):
        pass

    def error(self, message):
        raise self.Error(message)

    def exit(self, status=0, message=None):
        raise self.Error(status, message)

def _abuild_fetch(argv):
    getopts = _ParseOrRaise(
        allow_abbrev=False,
        add_help=False,
    )

    getopts.add_argument(
        "-d"
    )

    getopts.add_argument(
        "url", metavar="URL",
        nargs=1,
    )

    opts = getopts.parse_args(argv)

def _abuild_addgroup(argv):
    getopts = _ParseOrRaise(
        allow_abbrev=False,
        add_help=False,
    )

    getopts.add_argument(
        "-S", action="store_true",
        required=True,
    )

    opts = getopts.parse_args(argv)

def _abuild_adduser(argv):
    getopts = _ParseOrRaise(
        allow_abbrev=False,
        add_help=False,
    )

    getopts.add_argument(
        "-D", action="store_true",
        required=True,
    )
    getopts.add_argument(
        "-G",
    )
    getopts.add_argument(
        "-H", action="store_true",
        required=True,
    )
    getopts.add_argument(
        "-S", action="store_true",
        required=True,
    )

    opts = getopts.parse_args(argv)

def _apk_fetch(argv):
    getopts = _ParseOrRaise(
        allow_abbrev=False,
        add_help=False,
    )

    getopts.add_argument(
        "--quiet", "-q",
        action="store_true",
    )
    getopts.add_argument(
        "--repositories-file",
    )
    getopts.add_argument(
        "--simulate", "-s",
        action="store_true",
    )
    getopts.add_argument(
        "--stdout",
        action="store_true",
    )

    applets = getopts.add_subparsers(
        dest="applet",
    )

    fetch = applets.add_parser("fetch")
    fetch.add_argument(
        "--stdout",
        action="store_true",
    )
    fetch.add_argument(
        "packages", metavar="PACKAGE",
        nargs="+",
    )
    fetch.add_argument(
        "--quiet", "-q",
        action="store_true",
    )
    fetch.add_argument(
        "--repositories-file",
    )
    fetch.add_argument(
        "--simulate", "-s",
        action="store_true",
    )

    opts = getopts.parse_args(argv)

def _abuild_apk(argv):
    getopts = _ParseOrRaise(
        allow_abbrev=False,
        add_help=False,
    )

    getopts.add_argument(
        "--print-arch",
        action="store_true",
    )
    getopts.add_argument(
        "--quiet", "-q",
        action="store_true",
    )
    getopts.add_argument(
        "--repository", "-X",
    )
    getopts.add_argument(
        "--simulate", "-s",
        action="store_true",
    )
    getopts.add_argument(
        "--wait",
        type=int,
    )

    applets = getopts.add_subparsers(
        dest="applet",
    )

    add = applets.add_parser("add")
    add.add_argument(
        "--virtual", "-t",
        required=True,
    )
    add.add_argument(
        "--latest", "-l",
        action="store_true",
    )
    add.add_argument(
        "--upgrade", "-u",
        action="store_true",
    )
    add.add_argument(
        "packages", metavar="PACKAGE",
        nargs="+",
    )
    add.add_argument(
        "--quiet", "-q",
        action="store_true",
    )
    add.add_argument(
        "--repository", "-X",
    )
    add.add_argument(
        "--simulate", "-s",
        action="store_true",
    )
    add.add_argument(
        "--wait",
        type=int,
    )

    dele = applets.add_parser("del")
    dele.add_argument(
        "packages", metavar="PACKAGE",
        nargs="+",
    )
    dele.add_argument(
        "--quiet", "-q",
        action="store_true",
    )
    dele.add_argument(
        "--repository", "-X",
    )
    dele.add_argument(
        "--simulate", "-s",
        action="store_true",
    )
    dele.add_argument(
        "--wait",
        type=int,
    )

    # No arguments or options
    applets.add_parser("update")

    upgrade = applets.add_parser("upgrade")
    upgrade.add_argument(
        "--available", "-a",
        action="store_true",
    )
    upgrade.add_argument(
        "--latest", "-l",
        action="store_true",
    )
    upgrade.add_argument(
        "--quiet", "-q",
        action="store_true",
    )
    upgrade.add_argument(
        "--repository", "-X",
    )
    upgrade.add_argument(
        "--simulate", "-s",
        action="store_true",
    )
    upgrade.add_argument(
        "--wait",
        type=int,
    )

    opts = getopts.parse_args(argv)
    if opts.applet == "add":
        if not opts.virtual.startswith(".makedepends-"):
            getopts.error(f"invalid virtual name: {opts.virtual}")

    elif opts.applet == "del":
        if any(not i.startswith(".makedepends-") for i in opts.packages):
            getopts.error("can only remove makedepends virtual packages")

_parse = {
    "apk": ("apk", _apk_fetch),
    "abuild-apk": ("apk", _abuild_apk),
    "abuild-fetch": ("abuild-fetch", _abuild_fetch),
    "abuild-addgroup": ("addgroup", _abuild_addgroup),
    "abuild-adduser": ("adduser", _abuild_adduser),
}

@enum.unique
class RootProto(enum.IntFlag):
    SERVER = 1
    OK = SERVER | 4
    ERROR = SERVER | 8

    CLIENT = 2
    BOOTSTRAP = CLIENT | 4
    AMEND = CLIENT | 8

def _handle_pipe(sel, cdir, user_r, stdout_w, stderr_w, ret_w):
    user_f = open(
        user_r, buffering=1,
        encoding="utf-8", errors="replace",
        closefd=False,
    )

    try:
        argv = user_f.readline()
        argv = argv.strip()
        argv = shlex.split(argv)

        if not argv:
            _LOGGER.info("EOF - closing pipe")
            user_f.close()
            sel.unregister(user_r)
            for fd in (user_r, stdout_w, stderr_w, ret_w):
                os.close(fd)
            return

        cmd = argv[0]

        if cmd not in _parse:
            raise _ParseOrRaise.Error("Invalid command: " + cmd)
        _LOGGER.info("Received command: %r", argv)

        _parse[cmd][1](argv[1:])
        argv[0] = _parse[cmd][0]

        rc, _ = chroot(
            argv, cdir,
            net=True, ro_root=False,
            stdout=stdout_w, stderr=stderr_w
        )

    except (_ParseOrRaise.Error, NotImplementedError, OSError) as e:
        os.write(stderr_w, (str(e) + "\n").encode("utf-8", errors="replace"))
        os.write(ret_w, b"001\n")

    else:
        os.write(ret_w, b"%03d\n" % rc)

    user_f.close()

def _pass_fds(conn, msg, fds):
    assert len(fds) == _NUM_FDS
    assert len(msg) <= _BUF_SIZE

    conn.sendmsg(
        [msg],
        [(
            socket.SOL_SOCKET,
            socket.SCM_RIGHTS,
            struct.pack(_PASSFD_FMT, *fds),
        )],
    )

def _get_creds(conn):
    # pid_t, uid_t, gid_t
    creds = struct.Struct("iII")
    return creds.unpack(
        conn.getsockopt(
            socket.SOL_SOCKET,
            socket.SO_PEERCRED,
            creds.size,
        ),
    )

def _send_err(conn, msg):
    msg = msg.encode("utf-8")
    if len(msg) > _BUF_SIZE - 1:
        msg = msg[:-3] + b"..."
    conn.sendall(bytes([RootProto.ERROR]) + msg)

class RootException(Exception):
    pass

class RootConn(socketserver.StreamRequestHandler):
    def handle(self):
        cdir, _, _, _ = self.request.recvmsg(_BUF_SIZE)
        pid, uid, _ = _get_creds(self.request)

        if not cdir:
            return

        if len(cdir) < len(b"x /"):
            raise RootException(f"[{pid}] Message too short: {cdir!r}")

        if cdir[0] == RootProto.BOOTSTRAP:
            bootstrap = True
        elif cdir[0] == RootProto.AMEND:
            bootstrap = False
        else:
            raise RootException(f"[{pid}] Invalid message type: {cdir!r}")
        cdir = Path(cdir[1:].decode("utf-8", "replace"))

        if not cdir.is_absolute():
            raise RootException(f"[{pid}] Relative path: {cdir}")

        if not cdir.is_dir():
            raise RootException(f"[{pid}] Nonexistent chroot: {cdir}")

        owner = cdir.stat().st_uid
        if uid != owner:
            raise RootException(f"[{pid}] Chroot belongs to {owner}")

        chroot_init(cdir)

        user_r, user_w = os.pipe()
        stdout_r, stdout_w = os.pipe()
        stderr_r, stderr_w = os.pipe()
        ret_r, ret_w = os.pipe()
        sent = (user_w, stdout_r, stderr_r, ret_r)
        kept = (user_r, stdout_w, stderr_w, ret_w)

        _pass_fds(self.request, bytes([RootProto.OK]), sent)
        for fd in sent:
            os.close(fd)

        if bootstrap:
            try:
                rc = chroot_bootstrap(
                    cdir,
                    stdout=stdout_w, stderr=stderr_w,
                )
                os.write(ret_w, b"%03d\n" % rc)
            except BrokenPipeError:
                for fd in kept:
                    os.close(fd)
                _LOGGER.debug(f"[{pid}] Client exited prematurely")
                return

        self.server.sel.register(
            user_r, selectors.EVENT_READ,
            (_handle_pipe, self.server.sel, cdir, *kept),
        )

class RootServer(socketserver.UnixStreamServer):
    def __init__(self, sel):
        self.sel = sel

        try:
            _SOCK_PATH.unlink()
        except FileNotFoundError:
            pass
        oldmask = os.umask(0o007)
        super().__init__(str(_SOCK_PATH), RootConn)
        os.umask(oldmask)

    def handle_error(self, request, _):
        _, exc, _ = sys.exc_info()
        _LOGGER.error("%s", exc)

        try:
            _send_err(request, exc)
        except:
            pass

def listen():
    sel = selectors.DefaultSelector()
    sock = RootServer(sel)

    sel.register(
        sock.fileno(), selectors.EVENT_READ,
        (sock.handle_request,)
    )

    while True:
        for key, event in sel.select():
            key.data[0](*key.data[1:])

def client_init(cdir, bootstrap=False):
    cdir = Path(cdir)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(str(_SOCK_PATH))

    msgtype = RootProto.BOOTSTRAP if bootstrap else RootProto.AMEND
    msg = bytes([msgtype]) + bytes(cdir)
    assert len(msg) <= _BUF_SIZE

    sock.sendall(msg)
    msg, anc, _, _ = sock.recvmsg(_BUF_SIZE, _PASSFD_SIZE)
    if anc:
        anc = anc[0]
        assert anc[0] == socket.SOL_SOCKET
        assert anc[1] == socket.SCM_RIGHTS
        fds = struct.unpack(_PASSFD_FMT, anc[2])
    else:
        fds = tuple()

    return (RootProto(msg[0]), msg[1:], fds)
