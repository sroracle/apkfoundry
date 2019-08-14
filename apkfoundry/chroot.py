# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import enum       # Flag
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

APORTSDIR = "/af/git"
BUILDDIR = "/af/build"
REPODEST = "/af/packages"
JOBDIR = "/af/jobs"

_CFG = get_config("chroot")
_ROOTID = _CFG.getint("rootid")
_SUBID = _CFG.getint("subid")
_APK_STATIC = _CFG.getpath("apk")
_BWRAP = _CFG.getpath("bwrap")
_SRCDEST = _CFG.getpath("distfiles")

class ChrootDelete(enum.Flag):
    NEVER = 0
    DELETE = 1
    ALWAYS = DELETE | 2

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

def _chroot_delete(cdir):
    _LOGGER.info("deleting chroot")
    run("abuild-rmtemp", cdir)

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

def chroot_bootstrap(cdir, log=None):
    # Database must be initialized before repositories are added.
    shutil.copy(_APK_STATIC, cdir)
    args = ["/apk.static", "add", "--initdb"]
    rc, _ = chroot(args, cdir=cdir, ro_root=False, net=True, log=log)
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
    rc, _ = chroot(args, cdir=cdir, ro_root=False, net=True, log=log)

    # Cleanup bootstrap files
    (cdir / "apk.static").unlink()
    bak = etc_repo_f.with_suffix(".bak")
    shutil.copy(bak, etc_repo_f)
    bak.unlink()

    return rc

def chroot_init(cdir):
    cdir = Path(cdir)

    branch = cdir / "af/info/branch"
    if not branch.is_file():
        raise FileNotFoundError("/af/info/branch file is required")
    branch = branch.read_text().strip()
    repo = cdir / "af/info/repo"
    if not repo.is_file():
        raise FileNotFoundError("/af/info/repo file is required")
    repo = repo.read_text().strip()

    conf_d = cdir / APORTSDIR.lstrip("/") / ".apkfoundry" / branch

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

def chroot(cmd,
        cdir,
        net=False,
        ro_root=True,
        ro_git=True,
        delete=ChrootDelete.NEVER,
        log=None,
        root_fd=None,
        **kwargs):

    if log:
        kwargs["stdout"] = kwargs["stderr"] = log
    root_bind = "--ro-bind" if ro_root else "--bind"
    git_bind = "--ro-bind" if ro_git else "--bind"

    cdir = Path(cdir)
    if not cdir.exists():
        raise FileNotFoundError(f"cdir '{cdir}' does not exist")

    setuid = uid = os.getuid()
    setgid = gid = os.getgid()
    cdir_uid = os.stat(cdir).st_uid
    if uid != cdir_uid:
        if uid != _ROOTID:
            raise PermissionError(f"cdir belongs to {cdir_uid}")

        uid = cdir_uid
        gid = pwd.getpwuid(uid).pw_gid

        setuid = setgid = 0

    info_r, info_w = os.pipe()
    pipe_r, pipe_w = os.pipe()
    if "pass_fds" in kwargs:
        kwargs["pass_fds"].extend((pipe_r, info_w))
    else:
        kwargs["pass_fds"] = [pipe_r, info_w]

    args = [
        str(_BWRAP),
        "--unshare-user",
        "--userns-block-fd", str(pipe_r),
        "--info-fd", str(info_w),
        "--uid", str(setuid),
        "--gid", str(setgid),
        "--unshare-cgroup",
        "--unshare-ipc",
        "--unshare-pid",
        "--unshare-uts",
        root_bind, cdir, "/",
        "--dev-bind", "/dev", "/dev",
        "--proc", "/proc",
        "--bind", cdir / "tmp", "/tmp",
        "--bind", cdir / "var/tmp", "/var/tmp",
        "--bind", _SRCDEST, _SRCDEST,
        git_bind, cdir / APORTSDIR.lstrip("/"), APORTSDIR,
        "--bind", cdir / BUILDDIR.lstrip("/"), BUILDDIR,
        "--bind", cdir / REPODEST.lstrip("/"), REPODEST,
        "--ro-bind", cdir / JOBDIR.lstrip("/"), JOBDIR,
        "--ro-bind", str(LIBEXEC), "/usr/libexec/apkfoundry",
        "--setenv", "REPODEST", REPODEST,
        "--setenv", "SRCDEST", _SRCDEST,
        "--chdir", APORTSDIR,
    ]

    if root_fd:
        kwargs["pass_fds"].append(root_fd)
        args.extend((
            "--setenv", "AF_ROOT_FD", str(root_fd),
        ))

    if not net:
        args.append("--unshare-net")

    if setuid == 0:
        args.extend([
            "--cap-add", "CAP_CHOWN",
            # Used by apk_db_run_script
            "--cap-add", "CAP_SYS_CHROOT",
        ])

    setarchfile = cdir / ".apkfoundry/setarch"
    if setarchfile.is_file():
        args.extend(["setarch", setarchfile.read_text().strip()])

    args.extend(cmd)

    proc = subprocess.Popen(args, **kwargs)

    os.close(pipe_r)
    os.close(info_w)

    select.select([info_r], [], [])
    info = json.load(os.fdopen(info_r))
    retcodes = _userns_init(info["child-pid"], uid, gid)
    os.write(pipe_w, b"\n")
    os.close(pipe_w)

    proc.communicate()
    retcodes.append(proc.returncode)

    success = all(i == 0 for i in retcodes)

    if delete == ChrootDelete.NEVER:
        pass

    elif delete == ChrootDelete.DELETE:
        if success:
            _chroot_delete(cdir)

    elif delete == ChrootDelete.ALWAYS:
        _chroot_delete(cdir)

    if not success:
        _LOGGER.error("chroot failed with status %r!", retcodes)

    return (max(abs(i) for i in retcodes), proc)
