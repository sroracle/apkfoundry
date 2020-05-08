# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019-2020 Max Rees
# See LICENSE for more information.
import argparse     # ArgumentParser
import errno        # EBADF
import logging      # getLogger
import os           # close, umask, walk, write
import selectors    # DefaultSelector, EVENT_READ
import shutil       # copy2, move
import socketserver # ThreadingMixIn, StreamRequestHandler, UnixStreamServer
import subprocess   # DEVNULL, call
import sys          # exc_info
from pathlib import Path

import apkfoundry           # APK_STATIC, SYSCONFDIR
import apkfoundry.container # Container
import apkfoundry.socket    # SOCK_PATH, get_creds, recv_fds, send_retcode
import apkfoundry._util as _util

_LOGGER = logging.getLogger(__name__)

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

def _force_copytree(src, dst):
    src = Path(src)
    dst = Path(dst)

    copied_files = []

    for srcpath, dirnames, filenames in os.walk(src):
        srcpath = Path(srcpath)

        dstpath = dst / srcpath.relative_to(src)
        dstpath.mkdir(exist_ok=True)

        for dirname in dirnames:
            _LOGGER.debug("mkdir %s", dstpath / dirname)
            (dstpath / dirname).mkdir(exist_ok=True)

        for filename in filenames:
            _LOGGER.debug("cp %s -> %s", srcpath / filename, dstpath / filename)
            shutil.copy2(srcpath / filename, dstpath / filename)
            copied_files.append(dstpath / filename)

    return copied_files

def _bootstrap_prepare(cdir):
    bootstrap_files = _force_copytree(
        apkfoundry.SYSCONFDIR / "skel:bootstrap", cdir
    )

    (cdir / "dev").mkdir(exist_ok=True)
    (cdir / "tmp").mkdir(exist_ok=True)
    (cdir / "var/tmp").mkdir(exist_ok=True, parents=True)
    (cdir / "tmp").chmod(0o1777)
    (cdir / "var/tmp").chmod(0o1777)

    if (cdir / "af/info/cache").exists():
        (cdir / "etc/apk/cache").mkdir(parents=True, exist_ok=True)

    # --initdb will destroy this file >_<
    world_f = cdir / "etc/apk/world"
    if world_f.exists():
        shutil.move(world_f, world_f.with_suffix(".af-bak"))
        return bootstrap_files, world_f

    return bootstrap_files, None

def _bootstrap_clean(cdir, files):
    for filename in files:
        if filename.with_suffix(".apk-new").exists():
            shutil.move(filename.with_suffix(".apk-new"), filename)
        elif subprocess.call(
                [apkfoundry.APK_STATIC, "--root", cdir, "info",
                 "--who-owns", filename.relative_to(cdir)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            ) != 0:
            filename.unlink()

def _cont_bootstrap(cdir, **kwargs):
    cont = apkfoundry.container.Container(cdir)
    bootstrap_files, world_f = _bootstrap_prepare(cdir)

    # Initialize database
    args = ["/apk.static", "add", "--initdb"]
    rc, _ = cont.run(args, ro_root=False, net=True, bootstrap=True, **kwargs)
    if rc != 0:
        return rc

    if world_f:
        shutil.move(world_f.with_suffix(".af-bak"), world_f)

    # Install packages
    args = ["/apk.static", "--update-cache", "add", "--upgrade", "--latest"]
    rc, _ = cont.run(args, ro_root=False, net=True, bootstrap=True, **kwargs)

    _bootstrap_clean(cdir, bootstrap_files)

    return rc

def _cont_refresh(cdir):
    cdir = Path(cdir)

    branch = (cdir / "af/info/branch").read_text().strip()
    repo = (cdir / "af/info/repo").read_text().strip()
    arch = (cdir / "etc/apk/arch").read_text().strip()
    branchdir = _util.get_branchdir(
        cdir / "af/info/aportsdir", branch
    )

    for skel in (
            apkfoundry.SYSCONFDIR / "skel",
            branchdir / "skel",
            branchdir / f"skel:{repo}",
            branchdir / f"skel::{arch}",
            branchdir / f"skel:{repo}:{arch}",
        ):

        if not skel.is_dir():
            _LOGGER.debug("could not find %s", skel)
            continue

        _force_copytree(skel, cdir)

    abuild_conf = apkfoundry.SYSCONFDIR / "abuild.conf"
    if abuild_conf.is_file():
        shutil.copy2(abuild_conf, cdir / "etc/abuild.conf")

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
                argv, fds = apkfoundry.socket.recv_fds(self.request)
                self.pid, self.uid, _ = apkfoundry.socket.get_creds(self.request)
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
                if not self.cdir:
                    argv = argv[1:]
                    self._init(argv)
                    continue
                else:
                    self._err("Already initialized")
                    continue
            if not self.cdir:
                self._err("Must call af-init first")
                continue
            if cmd == "af-refresh":
                _cont_refresh(self.cdir)
                apkfoundry.socket.send_retcode(self.request, 0)
                continue

            if cmd not in _parse:
                self._err("Command not allowed: %s", cmd)
                continue

            _LOGGER.info(
                "[%d:%d] Received command: %s",
                self.uid, self.pid, " ".join(argv),
            )

            try:
                _parse[cmd][1](argv[1:])
            except _ParseOrRaise.Error as e:
                self._err("%s", e)
                continue
            argv[0] = _parse[cmd][0]

            try:
                cont = apkfoundry.container.Container(self.cdir)
                rc, _ = cont.run(
                    argv,
                    net=True, ro_root=False,
                    stdin=self.fds[0], stdout=self.fds[1], stderr=self.fds[2],
                )

                apkfoundry.socket.send_retcode(self.request, rc)
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
        opts = _ParseOrRaise(
            allow_abbrev=False,
            add_help=False,
        )
        opts.add_argument(
            "--bootstrap",
            action="store_true",
        )
        opts.add_argument(
            "--destroy",
            action="store_true",
        )
        opts.add_argument(
            "cdir", metavar="CDIR",
        )
        try:
            opts = opts.parse_args(argv)
        except _ParseOrRaise.Error as e:
            self._err("%s", e)
            return

        opts.cdir = Path(opts.cdir) # pylint: disable=attribute-defined-outside-init

        if not opts.cdir.is_absolute():
            self._err("Relative path: %s", opts.cdir)
            return

        if not opts.cdir.is_dir():
            self._err("Nonexistent container: %s", opts.cdir)
            return

        owner = opts.cdir.stat().st_uid
        if self.uid != owner and self.uid != _util.rootid().pw_uid:
            self._err("%s belongs to %s", opts.cdir, owner)
            return

        if opts.bootstrap and opts.destroy:
            self._err("cannot bootstrap and destroy at the same time")
            return

        self.cdir = opts.cdir # pylint: disable=attribute-defined-outside-init
        rc = 0

        if opts.bootstrap:
            _cont_refresh(self.cdir)
            rc = _cont_bootstrap(
                self.cdir,
                stdin=self.fds[0], stdout=self.fds[1], stderr=self.fds[2],
            )

        if opts.destroy:
            cont = apkfoundry.container.Container(self.cdir)
            for i in ("dev", "proc"):
                (self.cdir / i).mkdir(exist_ok=True)

            rc, _ = cont.run(
                ["/af/libexec/af-rm-container"],
                ro_root=False,
                skip_mounts=True,
                stdin=self.fds[0], stdout=self.fds[1], stderr=self.fds[2],
            )

        apkfoundry.socket.send_retcode(self.request, rc)

    def _err(self, fmt, *args):
        msg = fmt % args

        try:
            os.write(self.fds[2], msg.encode("utf-8") + b"\n")
        except OSError:
            pass

        try:
            apkfoundry.socket.send_retcode(self.request, 1)
        except ConnectionError:
            pass

        _LOGGER.error("[%d:%d] " + fmt, self.uid, self.pid, *args)

class RootServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    def __init__(self, sel):
        self.sel = sel

        try:
            apkfoundry.socket.SOCK_PATH.unlink()
        except FileNotFoundError:
            pass
        oldmask = os.umask(0o007)
        super().__init__(str(apkfoundry.socket.SOCK_PATH), RootConn)
        os.umask(oldmask)

    def handle_error(self, request, _):
        _, exc, _ = sys.exc_info()
        _LOGGER.exception("%s", exc)

        try:
            apkfoundry.socket.send_retcode(request, 1)
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
        for key, _ in sel.select():
            key.data[0](*key.data[1:])
