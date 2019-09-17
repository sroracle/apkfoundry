# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import argparse     # ArgumentParser
import errno        # EBADF
import logging      # getLogger
import os           # close, umask, write
import selectors    # DefaultSelector, EVENT_READ
import socketserver # ThreadingMixIn, StreamRequestHandler, UnixStreamServer
import sys          # exc_info
from pathlib import Path

from . import get_config
from .container import Container, cont_bootstrap, cont_refresh
from .socket import get_creds, recv_fds, send_retcode, SOCK_PATH

_LOGGER = logging.getLogger(__name__)
_CFG = get_config("container")
_ROOTID = _CFG.getint("rootid")

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
    getopts.add_argument(
        "group",
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
    getopts.add_argument(
        "user",
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
        nargs="*",
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

    fix = applets.add_parser("fix")
    fix.add_argument(
        "--depends", "-d",
        action="store_true",
    )
    fix.add_argument(
        "--reinstall", "-r",
        action="store_true",
    )
    fix.add_argument(
        "--xattr", "-x",
        action="store_true",
    )
    fix.add_argument(
        "--directory-permissions",
        action="store_true",
    )
    fix.add_argument(
        "--upgrade", "-u",
        action="store_true",
    )
    fix.add_argument(
        "packages", metavar="PACKAGE",
        nargs="*",
    )
    fix.add_argument(
        "--quiet", "-q",
        action="store_true",
    )
    fix.add_argument(
        "--repository", "-X",
    )
    fix.add_argument(
        "--simulate", "-s",
        action="store_true",
    )
    fix.add_argument(
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

class RootExc(Exception):
    pass

class RootConn(socketserver.StreamRequestHandler):
    def setup(self):
        super().setup()
        self.cdir = None
        self.fds = [-1, -1, -1]
        self.pid = self.uid = -1

    def handle(self):
        announced = False

        while True:
            self._close_fds()

            try:
                argv, fds = recv_fds(self.request)
                self.pid, self.uid, _ = get_creds(self.request)
            except ConnectionError:
                _LOGGER.info("[%d:%d] Disconnected", self.uid, self.pid)
                break
            if not argv:
                _LOGGER.info("[%d:%d] Disconnected", self.uid, self.pid)
                break

            if not announced:
                _LOGGER.info("[%d:%d] Connected", self.uid, self.pid)
                announced = True

            if not fds:
                self._err("No file descriptors given")
                continue
            self.fds = list(fds)

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
            elif cmd == "af-refresh":
                cont_refresh(self.cdir)
                send_retcode(self.request, 0)
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
                cont = Container(self.cdir)
                rc, _ = cont.run(
                    argv,
                    net=True, ro_root=False,
                    stdin=self.fds[0], stdout=self.fds[1], stderr=self.fds[2],
                )

                send_retcode(self.request, rc)
            except ConnectionError:
                pass

    def finish(self):
        self._close_fds()

    def _close_fds(self):
        for i, fd in enumerate(self.fds):
            if fd == -1:
                continue
            try:
                os.close(fd)
            except OSError as e:
                if e.errno != errno.EBADF:
                    raise
            self.fds[i] = -1

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
            self._err(f"Nonexistent container: {opts.cdir}")
            return

        owner = opts.cdir.stat().st_uid
        if self.uid != owner and self.uid != _ROOTID:
            self._err(f"{opts.cdir} belongs to {owner}")
            return

        self.cdir = opts.cdir
        cont_refresh(self.cdir)
        rc = 0

        if opts.bootstrap:
            rc = cont_bootstrap(
                self.cdir,
                stdin=self.fds[0], stdout=self.fds[1], stderr=self.fds[2],
            )

        send_retcode(self.request, rc)

    def _err(self, msg):
        try:
            os.write(self.fds[2], msg.encode("utf-8") + b"\n")
        except OSError:
            pass

        try:
            send_retcode(self.request, 1)
        except ConnectionError:
            pass

        msg = f"[{self.uid}:{self.pid}] {msg}"
        _LOGGER.error(msg)

class RootServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    def __init__(self, sel):
        self.sel = sel

        try:
            SOCK_PATH.unlink()
        except FileNotFoundError:
            pass
        oldmask = os.umask(0o007)
        super().__init__(str(SOCK_PATH), RootConn)
        os.umask(oldmask)

    def handle_error(self, request, _):
        _, exc, _ = sys.exc_info()
        _LOGGER.exception("%s", exc)

        try:
            send_retcode(request, 1)
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
