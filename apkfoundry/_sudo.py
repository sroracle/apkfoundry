# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019-2020 Max Rees
# See LICENSE for more information.
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

NUM_FDS = 3
PASSFD_FMT = NUM_FDS * "i"
PASSFD_SIZE = socket.CMSG_SPACE(struct.calcsize(PASSFD_FMT))
RC_FMT = "i"
BUF_SIZE = 4096

def abuild_fetch(argv):
    expected_argv = (
        "-d",
        "/af/distfiles",
        ...,
    )

    if len(argv) != len(expected_argv):
        raise ValueError("apkfoundry: abuild-fetch: invalid usage")

    for arg, expected in zip(argv, expected_argv):
        if expected not in (..., arg):
            raise ValueError(
                "apkfoundry: abuild-fetch: %s: invalid argument" % arg,
            )

def apk(argv):
    invalid_opts = (
        "--allow-untrusted",
        "--keys-dir",
    )

    for i in invalid_opts:
        if i in argv:
            raise ValueError("apkfoundry: apk: %s: not allowed option" % i)

COMMANDS = {
    "apk": ("/sbin/apk", apk),
    "abuild-apk": ("/sbin/apk", apk),
    "abuild-fetch": ("/usr/bin/abuild-fetch", abuild_fetch),
    "abuild-addgroup": ("/usr/sbin/addgroup", lambda _: ...),
    "abuild-adduser": ("/usr/sbin/adduser", lambda _: ...),
}

def recv_fds(conn):
    msg, anc, _, _ = conn.recvmsg(
        BUF_SIZE, PASSFD_SIZE
    )

    for cmsg in anc:
        if cmsg[0:2] != (socket.SOL_SOCKET, socket.SCM_RIGHTS):
            continue
        fds = struct.unpack(PASSFD_FMT, cmsg[2])
        break
    else:
        fds = tuple()

    return (msg, fds)

def send_retcode(conn, rc):
    conn.send(struct.pack(RC_FMT, rc))

def client_init(cdir):
    server, client = socket.socketpair()
    sudo_thread = threading.Thread(
        target=SudoConn,
        args=(server, cdir),
        daemon=True,
    )

    sudo_thread.start()
    return client

class SudoConn(socketserver.StreamRequestHandler):
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

            if cmd not in COMMANDS:
                self._err("Command not allowed: %s", cmd)
                continue

            _LOGGER.debug("Received command: %s", " ".join(argv))

            try:
                COMMANDS[cmd][1](argv[1:])
            except ValueError as e:
                self._err("%s", e)
                continue
            argv[0] = COMMANDS[cmd][0]

            try:
                cont = apkfoundry.container.Container(self.cdir, sudo=False)
                rc, _ = cont.run(
                    argv,
                    su=True, net=True, ro_root=False, skip_refresh=True,
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
