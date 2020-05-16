# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019-2020 Max Rees
# See LICENSE for more information.
import argparse     # ArgumentParser
import errno        # EBADF
import logging      # getLogger
import os           # close, write
import socket       # CMSG_SPACE, SOL_SOCKET, SCM_RIGHTS, socketpair
import socketserver # StreamRequestHandler
import struct       # calcsize, pack, unpack
import threading    # Thread
from pathlib import Path

import apkfoundry.container # Container

_LOGGER = logging.getLogger(__name__)

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

    getopts.parse_args(argv)

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

    getopts.parse_args(argv)

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

    getopts.parse_args(argv)

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

    getopts.parse_args(argv)

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

def recv_fds(conn):
    msg, anc, _, _ = conn.recvmsg(
        _BUF_SIZE, _PASSFD_SIZE
    )

    for cmsg in anc:
        if cmsg[0:2] != (socket.SOL_SOCKET, socket.SCM_RIGHTS):
            continue
        fds = struct.unpack(_PASSFD_FMT, cmsg[2])
        break
    else:
        fds = tuple()

    return (msg, fds)

def send_retcode(conn, rc):
    conn.send(struct.pack(_RC_FMT, rc))

def client_init(cdir):
    server, client = socket.socketpair()
    root_thread = threading.Thread(
        target=RootConn,
        args=(server, cdir),
        daemon=True,
    )

    root_thread.start()
    return client

class RootConn(socketserver.StreamRequestHandler):
    def __init__(self, sock, cdir):
        self.cdir = Path(cdir)
        super().__init__(sock, None, None)

    def setup(self):
        super().setup()
        self.fds = [-1, -1, -1]

    def handle(self):
        announced = False

        while True:
            self._close_fds()

            try:
                argv, fds = recv_fds(self.request)
            except ConnectionError:
                _LOGGER.debug("Disconnected")
                break
            if not argv:
                _LOGGER.debug("Disconnected")
                break

            if not announced:
                _LOGGER.debug("Connected")
                announced = True

            if not fds:
                self._err("No file descriptors given")
                continue
            self.fds = list(fds)

            argv = argv.decode("utf-8")
            argv = argv.split("\0")
            cmd = argv[0]

            if cmd not in _parse:
                self._err("Command not allowed: %s", cmd)
                continue

            _LOGGER.debug("Received command: %s", " ".join(argv))

            try:
                _parse[cmd][1](argv[1:])
            except _ParseOrRaise.Error as e:
                self._err("%s", e)
                continue
            argv[0] = _parse[cmd][0]

            try:
                cont = apkfoundry.container.Container(self.cdir, rootd=False)
                rc, _ = cont.run(
                    argv,
                    root=True, net=True, ro_root=False,
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

    def _err(self, fmt, *args):
        msg = fmt % args

        try:
            os.write(self.fds[2], msg.encode("utf-8") + b"\n")
        except OSError:
            pass

        try:
            send_retcode(self.request, 1)
        except ConnectionError:
            pass

        _LOGGER.error(fmt, *args)
