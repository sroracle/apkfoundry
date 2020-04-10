# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019-2020 Max Rees
# See LICENSE for more information.
import logging      # getLogger
import socket       # socket, various constants
import struct       # calcsize, pack, Struct, unpack
import sys          # std*

from . import HOME

_LOGGER = logging.getLogger(__name__)

_NUM_FDS = 3
_PASSFD_FMT = _NUM_FDS * "i"
_PASSFD_SIZE = socket.CMSG_SPACE(struct.calcsize(_PASSFD_FMT))
_RC_FMT = "i"
_BUF_SIZE = 4096

SOCK_PATH = HOME / "root.sock"

def send_fds(conn, msg, fds):
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

def get_creds(conn):
    # pid_t, uid_t, gid_t
    creds = struct.Struct("iII")
    return creds.unpack(
        conn.getsockopt(
            socket.SOL_SOCKET,
            socket.SO_PEERCRED,
            creds.size,
        ),
    )

def send_retcode(conn, rc):
    conn.send(struct.pack(_RC_FMT, rc))

def recv_retcode(conn):
    rc = conn.recv(_BUF_SIZE)
    (rc,) = struct.unpack(_RC_FMT, rc)
    return rc

def client_init(cdir, bootstrap=False, stdin=None, stdout=None, stderr=None):
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    conn.connect(str(SOCK_PATH))

    if stdin is None:
        stdin = sys.stdin
    if stdout is None:
        stdout = sys.stdout
    if stderr is None:
        stderr = sys.stderr

    msg = ["af-init"]
    if bootstrap:
        msg.append("--bootstrap")
    msg.append(str(cdir))
    msg = "\0".join(msg).encode("utf-8")

    send_fds(
        conn,
        msg,
        [
            stdin.fileno(),
            stdout.fileno(),
            stderr.fileno(),
        ],
    )

    rc = recv_retcode(conn)
    return (rc, conn)

def client_refresh(conn, stdin=None, stdout=None, stderr=None):
    if stdin is None:
        stdin = sys.stdin
    if stdout is None:
        stdout = sys.stdout
    if stderr is None:
        stderr = sys.stderr

    send_fds(
        conn,
        b"af-refresh",
        [
            stdin.fileno(),
            stdout.fileno(),
            stderr.fileno(),
        ],
    )

    rc = recv_retcode(conn)
    return rc
