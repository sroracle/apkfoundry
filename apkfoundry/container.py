# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import enum       # Enum
import fileinput  # FileInput
import getpass    # getuser
import json       # load
import logging    # getLogger
import os         # close, getuid, getgid, pipe, stat, write
import pwd        # getpwuid
import select     # select
import shlex      # quote
import shutil     # copy, copytree, rmtree
import socket     # gethostname
import subprocess # call, Popen
from pathlib import Path

from . import get_config, LIBEXEC, run

_LOGGER = logging.getLogger(__name__)

APORTSDIR = "/af/aports"
BUILDDIR = "/af/build"
REPODEST = "/af/packages"
JOBDIR = "/af/jobs"

_CFG = get_config("container")
_ROOTID = _CFG.getint("rootid")
_SUBID = _CFG.getint("subid")
_APK_STATIC = _CFG.getpath("apk")
_BWRAP = _CFG.getpath("bwrap")

_MOUNTS = {
    "aports": "/af/aports",
    "packages": "/af/packages",
    "srcdest": "/var/cache/distfiles",
}

class Delete(enum.Enum):
    NEVER = 0
    ON_SUCCESS = 1
    ALWAYS = 2

def _idmap(userid):
    assert _ROOTID != userid, "root ID cannot match user ID"

    args = [
        "0",
        str(_ROOTID),
        "1",
        str(userid),
        str(userid),
        "1",

        "1",
        str(_SUBID + 1),
        str(userid - 2 + 1),

        str(userid + 1),
        str(_SUBID + userid + 1),
        str(65534 - (userid + 1)),
    ]

    assert len(args) % 3 == 0, "map must have 3 entries per line"
    assert len(args) / 3 < 5, "map may not have more than 3 lines"

    return args

def _userns_init(pid, uid, gid):
    retcodes = []

    retcodes.append(
        subprocess.call([
            "newuidmap", str(pid),
            *_idmap(uid),
        ])
    )
    if retcodes[-1] != 0:
        return retcodes

    retcodes.append(
        subprocess.call([
            "newgidmap", str(pid),
            *_idmap(gid),
        ])
    )

    return retcodes


def _checkfile(path):
    if not path.is_file():
        raise FileNotFoundError(f"Missing {path}")

    return path

def _checkdir(path):
    if not path.is_dir():
        raise FileNotFoundError(f"Missing {path}")

    return path

def _checkfile_repo(path, repo):
    path = path.with_suffix("." + repo)
    if not path.is_file():
        path = path.with_suffix("")
        _checkfile(path)

    return path

def cont_refresh(cdir):
    cdir = Path(cdir)

    branch = cdir / "af/info/branch"
    if not branch.is_file():
        raise FileNotFoundError("/af/info/branch file is required")
    branch = branch.read_text().strip()
    repo = cdir / "af/info/repo"
    if not repo.is_file():
        raise FileNotFoundError("/af/info/repo file is required")
    repo = repo.read_text().strip()

    conf_d = cdir / "af/info/aports/.apkfoundry" / branch

    keys_d = _checkdir(conf_d / "keys")
    try:
        shutil.rmtree(cdir / "etc/apk/keys")
    except FileNotFoundError:
        pass
    shutil.copytree(
        keys_d, cdir / "etc/apk/keys",
        copy_function=shutil.copy,
    )

    arch_f = cdir / "af/info/arch"
    if not arch_f.is_file():
        raise FileNotFoundError("/af/info/arch file is required")
    arch = arch_f.read_text().strip()
    shutil.copy(arch_f, cdir / "etc/apk/arch")

    repo_f = _checkfile_repo(conf_d / "repositories", repo)
    shutil.copy(repo_f, cdir / "etc/apk/repositories")

    world_f = _checkfile(conf_d / "world")
    shutil.copy(world_f, cdir / "etc/apk/world")

    abuild_f = _checkfile(Path(f"/etc/apkfoundry/abuild.{arch}.conf"))
    shutil.copy(abuild_f, cdir / "etc/abuild.conf")

    localtime = cdir / "etc/localtime"
    try:
        localtime.symlink_to("../usr/share/zoneinfo/UTC")
    except FileExistsError:
        localtime.unlink()
        localtime.symlink_to("../usr/share/zoneinfo/UTC")

    shutil.copy("/etc/passwd", cdir / "etc")
    shutil.copy("/etc/group", cdir / "etc")
    shutil.copy("/etc/resolv.conf", cdir / "etc")

class Container:
    __slots__ = (
        "cdir",
        "root_fd",

        "_owneruid",
        "_ownergid",
        "_setuid",
        "_setgid",
    )

    def __init__(self, cdir, *, root_fd=None):
        self.cdir = Path(cdir)
        if not self.cdir.exists():
            raise FileNotFoundError(f"'{self.cdir}' does not exist")

        self._setuid = self._owneruid = os.getuid()
        self._setgid = self._ownergid = os.getgid()
        cdir_uid = os.stat(self.cdir).st_uid
        if self._owneruid != cdir_uid:
            if self._owneruid != _ROOTID:
                raise PermissionError(f"'{self.cdir}' belongs to '{cdir_uid}'")

            self._owneruid = cdir_uid
            self._ownergid = pwd.getpwuid(self._owneruid).pw_gid
            self._setuid = self._setgid = 0

        self.root_fd = root_fd

    def delete(self):
        raise NotImplementedError

    def run(self,
            cmd,
            *,
            delete=Delete.NEVER,
            net=False,
            ro_aports=True,
            ro_root=True,
            **kwargs):

        root_bind = "--ro-bind" if ro_root else "--bind"
        aports_bind = "--ro-bind" if ro_aports else "--bind"

        info_r, info_w = os.pipe()
        pipe_r, pipe_w = os.pipe()
        if "pass_fds" in kwargs:
            kwargs["pass_fds"].extend((pipe_r, info_w))
        else:
            kwargs["pass_fds"] = [pipe_r, info_w]

        mounts = _MOUNTS.copy()
        for mount in mounts:
            mounts[mount] = (self.cdir / "af/info" / mount).resolve(strict=False)

        args = [
            str(_BWRAP),
            "--unshare-user",
            "--userns-block-fd", str(pipe_r),
            "--info-fd", str(info_w),
            "--uid", str(self._setuid),
            "--gid", str(self._setgid),
            "--unshare-cgroup",
            "--unshare-ipc",
            "--unshare-pid",
            "--unshare-uts",
            root_bind, self.cdir, "/",
            "--dev-bind", "/dev", "/dev",
            "--proc", "/proc",
            "--bind", self.cdir / "tmp", "/tmp",
            "--bind", self.cdir / "var/tmp", "/var/tmp",
            "--bind", mounts["srcdest"], "/var/cache/distfiles",
            aports_bind, mounts["aports"], APORTSDIR,
            "--bind", self.cdir / BUILDDIR.lstrip("/"), BUILDDIR,
            "--bind", self.cdir / REPODEST.lstrip("/"), REPODEST,
            "--ro-bind", self.cdir / JOBDIR.lstrip("/"), JOBDIR,
            "--ro-bind", str(LIBEXEC), "/af/libexec",
            "--setenv", "REPODEST", REPODEST,
            "--setenv", "SRCDEST", "/var/cache/distfiles",
            "--setenv", "SUDO_APK", "/af/libexec/af-req-root abuild-apk",
            "--setenv", "ADDUSER", "/af/libexec/af-req-root abuild-adduser",
            "--setenv", "ADDGROUP", "/af/libexec/af-req-root abuild-addgroup",
            "--setenv", "ABUILD_FETCH", "/af/libexec/af-req-root abuild-fetch",
            "--chdir", APORTSDIR,
        ]

        if self.root_fd:
            kwargs["pass_fds"].append(self.root_fd)
            args.extend((
                "--setenv", "AF_ROOT_FD", str(self.root_fd),
            ))

        if not net:
            args.append("--unshare-net")

        if self._setuid == 0:
            args.extend([
                "--cap-add", "CAP_CHOWN",
                # Used by apk_db_run_script
                "--cap-add", "CAP_SYS_CHROOT",
            ])

        setarchfile = self.cdir / ".apkfoundry/setarch"
        if setarchfile.is_file():
            args.extend(["setarch", setarchfile.read_text().strip()])

        args.extend(cmd)

        proc = subprocess.Popen(args, **kwargs)

        os.close(pipe_r)
        os.close(info_w)

        select.select([info_r], [], [])
        info = json.load(os.fdopen(info_r))
        retcodes = _userns_init(
            info["child-pid"], self._owneruid, self._ownergid
        )
        os.write(pipe_w, b"\n")
        os.close(pipe_w)

        proc.communicate()
        retcodes.append(proc.returncode)

        success = all(i == 0 for i in retcodes)

        if delete == Delete.NEVER:
            pass

        elif delete == Delete.ON_SUCCESS:
            if success:
                self.delete()

        elif delete == Delete.ALWAYS:
            self.delete()

        if not success:
            _LOGGER.debug("container failed with status %r!", retcodes)

        return (max(abs(i) for i in retcodes), proc)

def cont_bootstrap(cdir):
    cont = Container(cdir)

    # Database must be initialized before repositories are added.
    shutil.copy(_APK_STATIC, cdir)
    args = ["/apk.static", "add", "--initdb"]
    rc, _ = cont.run(args, ro_root=False, net=True)
    if rc:
        return rc

    # Use http instead of https when bootstrapping since ca-certificates
    # will be unavailable
    etc_repo_f = cdir / "etc/apk/repositories"
    with fileinput.FileInput(
            files=(str(etc_repo_f),),
            inplace=True, backup=".bak") as f:
        for line in f:
            if line.startswith("https"):
                line = line.replace("https", "http", 1)

            print(line, end="")

    args = ["/apk.static", "--update-cache", "add", "--upgrade", "--latest"]
    rc, _ = cont.run(args, ro_root=False, net=True)

    # Cleanup bootstrap files
    (cdir / "apk.static").unlink()
    bak = etc_repo_f.with_suffix(".bak")
    shutil.copy(bak, etc_repo_f)
    bak.unlink()

    return rc
