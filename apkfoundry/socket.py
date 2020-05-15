# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019-2020 Max Rees
# See LICENSE for more information.
import logging      # getLogger
import socket       # CMSG_SPACE, SOL_SOCKET, SCM_RIGHTS, socketpair
import struct       # calcsize, pack, unpack
import threading    # Thread

import apkfoundry.root # RootServer

_LOGGER = logging.getLogger(__name__)

_NUM_FDS = 3
_PASSFD_FMT = _NUM_FDS * "i"
_PASSFD_SIZE = socket.CMSG_SPACE(struct.calcsize(_PASSFD_FMT))
_RC_FMT = "i"
_BUF_SIZE = 4096

def recv_fds(conn):
    msg, anc, _, _ = conn.recvmsg(
        _BUF_SIZE, _PASSFD_SIZE
    )

    if anc:
        anc = anc[0]
        assert anc[0] == socket.SOL_SOCKET
        assert anc[1] == socket.SCM_RIGHTS
        fds = struct.unpack(_PASSFD_FMT, anc[2])
    else:
        fds = tuple()

    return (msg, fds)

def send_retcode(conn, rc):
    conn.send(struct.pack(_RC_FMT, rc))

def client_init(cdir):
    server, client = socket.socketpair()
    root_thread = threading.Thread(
        target=apkfoundry.root.RootConn,
        args=(server, cdir),
        daemon=True,
    )

    root_thread.start()
    return client
