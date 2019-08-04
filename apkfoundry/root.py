# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import argparse     # ArgumentParser
import logging      # getLogger
import os           # umask, write
import selectors    # DefaultSelector, EVENT_READ
import shlex        # quote, split
import socket       # socket, various constants
import socketserver # ThreadingMixIn, StreamRequestHandler, UnixStreamServer
import struct       # calcsize, pack, Struct, unpack
import sys          # exc_info, exit, std*
from pathlib import Path

from . import get_config
from .chroot import chroot, chroot_bootstrap, chroot_init

_LOGGER = logging.getLogger(__name__)
_CFG = get_config("chroot")
_ROOTID = _CFG.getint("rootid")
_SOCK_PATH = _CFG.getpath("socket")
_NUM_FDS = 3
_PASSFD_FMT = _NUM_FDS * "i"
_PASSFD_SIZE = socket.CMSG_SPACE(struct.calcsize(_PASSFD_FMT))
_RC_FMT = "i"
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

def _recv_retcode(conn):
    rc, _, _, _ = conn.recvmsg(_BUF_SIZE)
    (rc,) = struct.unpack(_RC_FMT, rc)
    return rc

def _send_retcode(conn, rc):
    conn.sendmsg(
        [struct.pack(_RC_FMT, rc)],
    )

def _recv_fds(anc):
    if anc:
        anc = anc[0]
        assert anc[0] == socket.SOL_SOCKET
        assert anc[1] == socket.SCM_RIGHTS
        fds = struct.unpack(_PASSFD_FMT, anc[2])
    else:
        fds = tuple()

    return fds

def _send_fds(conn, msg, fds):
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

class RootExc(Exception):
    pass

class RootConn(socketserver.StreamRequestHandler):
    def setup(self):
        super().setup()
        self.cdir = None
        self.stdin = self.stdout = self.stderr = None
        self.pid = self.uid = -1

    def handle(self):
        announced = False

        while True:
            try:
                argv, anc, _, _ = self.request.recvmsg(
                    _BUF_SIZE, _PASSFD_SIZE
                )
                self.pid, self.uid, _ = _get_creds(self.request)
            except ConnectionError:
                _LOGGER.info("[%d:%d] Disconnected", self.uid, self.pid)
                break
            if not argv:
                _LOGGER.info("[%d:%d] Disconnected", self.uid, self.pid)
                break

            if not announced:
                _LOGGER.info("[%d:%d] Connected", self.uid, self.pid)
                announced = True

            fds = _recv_fds(anc)
            if not fds:
                self._err("No file descriptors given")
                continue
            self.stdin, self.stdout, self.stderr = fds

            argv = argv.decode("utf-8")
            argv = argv.split("\0")
            cmd = argv[0]

            if cmd == "af-init":
                argv = argv[1:]
                self._init(argv)
                continue
            elif not self.cdir:
                self._err("Must call af-init first")
                continue

            if cmd not in _parse:
                self._err("Command not allowed: " + cmd)
                continue

            _LOGGER.info("[%d:%d] Received command: %r", self.uid, self.pid, argv)

            try:
                _parse[cmd][1](argv[1:])
            except _ParseOrRaise.Error as e:
                self._err(str(e))
                continue
            argv[0] = _parse[cmd][0]

            try:
                rc, _ = chroot(
                    argv, self.cdir,
                    net=True, ro_root=False,
                    stdin=self.stdin, stdout=self.stdout, stderr=self.stderr,
                )

                _send_retcode(self.request, rc)
            except ConnectionError:
                pass

    def _init(self, argv):
        getopts = _ParseOrRaise(
            allow_abbrev=False,
            add_help=False,
        )
        getopts.add_argument(
            "--bootstrap",
            action="store_true",
        )
        getopts.add_argument(
            "cdir", metavar="CDIR",
        )
        try:
            opts = getopts.parse_args(argv)
        except _ParseOrRaise.Error as e:
            self._err(e)
            return

        opts.cdir = Path(opts.cdir)

        if not opts.cdir.is_absolute():
            self._err(f"Relative path: {opts.cdir}")
            return

        if not opts.cdir.is_dir():
            self._err(f"Nonexistent chroot: {opts.cdir}")
            return

        owner = opts.cdir.stat().st_uid
        if self.uid != owner and self.uid != _ROOTID:
            self._err(f"{opts.cdir} belongs to {owner}")
            return

        self.cdir = opts.cdir
        chroot_init(self.cdir)
        rc = 0

        if opts.bootstrap:
            rc = chroot_bootstrap(
                self.cdir,
                stdin=self.stdin, stdout=self.stdout, stderr=self.stderr,
            )

        _send_retcode(self.request, rc)

    def _err(self, msg):
        try:
            os.write(self.stderr, msg.encode("utf-8") + b"\n")
        except OSError:
            pass

        try:
            _send_retcode(self.request, 1)
        except ConnectionError:
            pass

        msg = f"[{self.uid}:{self.pid}] {msg}"
        _LOGGER.error(msg)

class RootServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
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
        _LOGGER.exception("%s", exc)

        try:
            _send_retcode(request, 1)
        except ConnectionError:
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
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.connect(str(_SOCK_PATH))

    argv = "af-init"
    if bootstrap:
        argv += "\0--bootstrap"
    argv += "\0" + cdir
    argv = argv.encode("utf-8")
    msg = argv

    _send_fds(
        sock,
        msg,
        [
            sys.stdin.fileno(),
            sys.stdout.fileno(),
            sys.stderr.fileno(),
        ],
    )

    rc = _recv_retcode(sock)
    if rc != 0:
        sys.exit(rc)

    return sock
