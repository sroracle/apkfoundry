# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import enum       # Enum
import getpass    # getuser
import json       # load
import logging    # getLogger
import os         # close, environ, getuid, getgid, pipe, stat, walk, write
import pwd        # getpwuid
import select     # select
import shlex      # quote
import shutil     # chown, copy2, copytree
import socket     # gethostname
import subprocess # call, Popen
from pathlib import Path

from . import get_config, LIBEXEC, run, SITE_CONF
from .socket import client_refresh

BUILDDIR = "/af/build"
JOBDIR = "/af/jobs"
MOUNTS = {
    "aportsdir": "/af/aports",
    "jobsdir": "/af/jobs",
    "repodest": "/af/repos",
    "srcdest": "/var/cache/distfiles",
}

_LOGGER = logging.getLogger(__name__)

_KEEP_ENV = (
    "TERM",
)

_APK_STATIC = SITE_CONF / "skel.bootstrap/apk.static"
_CFG = get_config("container")
_ROOTID = _CFG.getint("rootid")
_SUBID = _CFG.getint("subid")

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

class Container:
    __slots__ = (
        "cdir",
        "rootd_conn",

        "_owneruid",
        "_ownergid",
        "_setuid",
        "_setgid",
    )

    def __init__(self, cdir, *, rootd_conn=None):
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

        self.rootd_conn = rootd_conn

    def delete(self):
        raise NotImplementedError

    def run(self,
            cmd,
            *,
            delete=Delete.NEVER,
            bootstrap=False,
            jobdir=None,
            net=False,
            repo=None,
            ro_aports=True,
            ro_root=True,
            skip_rootd=False,
            setsid=True,
            **kwargs):

        root_bind = "--ro-bind" if ro_root else "--bind"
        aports_bind = "--ro-bind" if ro_aports else "--bind"

        info_r, info_w = os.pipe()
        pipe_r, pipe_w = os.pipe()
        if "pass_fds" in kwargs:
            kwargs["pass_fds"].extend((pipe_r, info_w))
        else:
            kwargs["pass_fds"] = [pipe_r, info_w]

        mounts = MOUNTS.copy()
        for mount in mounts:
            mounts[mount] = self.cdir / "af/info" / mount
            if not mounts[mount].is_symlink():
                raise FileNotFoundError(mounts[mount])

        if "env" not in kwargs:
            kwargs["env"] = {}
        kwargs["env"].update({
            name: os.environ[name] for name in _KEEP_ENV \
            if name in os.environ and name not in kwargs["env"]
        })
        kwargs["env"].update({
            "LOGNAME": getpass.getuser(),
            "USER": getpass.getuser(),
            "UID": str(self._setuid),
            "PATH": "/usr/bin:/usr/sbin:/bin:/sbin",
            "SRCDEST": MOUNTS["srcdest"],
            "APORTSDIR": MOUNTS["aportsdir"],
            "REPODEST": MOUNTS["repodest"],
            "ABUILD_GIT": "git -C /af/aports",
            "ABUILD_FETCH": "/af/libexec/af-req-root abuild-fetch",
            "ADDGROUP": "/af/libexec/af-req-root abuild-addgroup",
            "ADDUSER": "/af/libexec/af-req-root abuild-adduser",
            "SUDO_APK": "/af/libexec/af-req-root abuild-apk",
        })

        args = [
            SITE_CONF / "bwrap.nosuid",
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
            aports_bind, mounts["aportsdir"], MOUNTS["aportsdir"],
            "--ro-bind", mounts["jobsdir"], MOUNTS["jobsdir"],
            "--bind", mounts["repodest"], MOUNTS["repodest"],
            "--bind", mounts["srcdest"], MOUNTS["srcdest"],
            "--bind", self.cdir / BUILDDIR.lstrip("/"), BUILDDIR,
            "--ro-bind", str(LIBEXEC), "/af/libexec",
            "--chdir", MOUNTS["aportsdir"],
        ]

        if repo:
            (self.cdir / "af/info/repo").write_text(repo.strip())

        if self.rootd_conn and not skip_rootd:
            rc = client_refresh(
                self.rootd_conn,
                **{
                    k: v for k, v in kwargs.items() \
                    if k in ("stdin", "stdout", "stderr")
                },
            )
            if rc != 0:
                _LOGGER.debug("failed to refresh container")
                return (rc, None)

            kwargs["pass_fds"].append(self.rootd_conn.fileno())
            args.extend((
                "--setenv", "AF_ROOT_FD", str(self.rootd_conn.fileno()),
            ))

        if jobdir is not None:
            args.extend([
                "--bind", Path(mounts["jobsdir"]) / str(jobdir),
                Path(MOUNTS["jobsdir"]) / str(jobdir),
            ])

        if not net:
            args.append("--unshare-net")

        if self._setuid == 0:
            args.extend([
                "--cap-add", "CAP_CHOWN",
                "--cap-add", "CAP_DAC_OVERRIDE",
                # Required to restore security file caps during package installation
                # On Linux 4.14+ these caps are tied to the user namespace in which
                # they are created
                "--cap-add", "CAP_SETFCAP",
                # Used by apk_db_run_script
                "--cap-add", "CAP_SYS_CHROOT",
            ])

        if setsid:
            args.append("--new-session")

        setarch_f = self.cdir / "af/info/setarch"
        if setarch_f.is_file() and not bootstrap:
            args.extend(["setarch", setarch_f.read_text().strip()])

        args.extend(cmd)

        proc = subprocess.Popen(args, **kwargs)

        os.close(pipe_r)
        os.close(info_w)

        select.select([info_r], [], [])
        info = json.load(os.fdopen(info_r))
        retcodes = _userns_init(
            info["child-pid"], self._owneruid, self._ownergid,
        )
        os.write(pipe_w, b"\n")
        os.close(pipe_w)

        proc.stdout, proc.stderr = proc.communicate()
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

def cont_make(
        cdir,
        branch,
        repo,
        *,
        arch=None,
        setarch=None,
        mounts=None):

    cdir = Path(cdir)
    cdir.mkdir()
    shutil.chown(cdir, group="apkfoundry")
    cdir.chmod(0o770)

    for mount in MOUNTS.values():
        (cdir / mount.lstrip("/")).mkdir(parents=True)

    for i in ("var", "var/cache", "var/cache/distfiles"):
        shutil.chown(cdir / i, group="apkfoundry")
        (cdir / i).chmod(0o775)

    (cdir / BUILDDIR.lstrip("/")).mkdir(parents=True, exist_ok=True)
    (cdir / JOBDIR.lstrip("/")).mkdir(parents=True, exist_ok=True)

    af_info = cdir / "af/info"
    af_info.mkdir(parents=True)

    (cdir / "af/libexec").mkdir()

    (af_info / "branch").write_text(branch.strip())
    (af_info / "repo").write_text(repo.strip())

    if arch is None:
        arch = subprocess.check_output(
            [_APK_STATIC, "--print-arch"],
            encoding="utf-8",
        )
    (cdir / "af/info/arch").write_text(arch.strip())

    if setarch:
        (cdir / "af/info/setarch").write_text(setarch.strip())

    if mounts is None:
        mounts = {}

    for mount in mounts:
        if mount not in MOUNTS:
            raise ValueError(f"Unknown mount '{mount}'")
        if not mounts[mount]:
            continue

        (cdir / "af/info" / mount).symlink_to(mounts[mount])

    for mount in MOUNTS:
        if mount in mounts:
            continue

        (cdir / "af/info" / mount).symlink_to(
            cdir / MOUNTS[mount].lstrip("/")
        )

def cont_bootstrap(cdir, **kwargs):
    cont = Container(cdir)
    bootstrap_files = _force_copytree(SITE_CONF / "skel.bootstrap", cdir)

    (cdir / "dev").mkdir()
    (cdir / "tmp").mkdir()
    (cdir / "var/tmp").mkdir(parents=True)
    (cdir / "tmp").chmod(0o1777)
    (cdir / "var/tmp").chmod(0o1777)

    world_f = cdir / "etc/apk/world"
    if world_f.exists():
        shutil.move(world_f, world_f.with_suffix(".af-bak"))
    args = ["/apk.static", "add", "--initdb"]
    rc, _ = cont.run(args, ro_root=False, net=True, bootstrap=True, **kwargs)
    if rc != 0:
        return rc
    if world_f.with_suffix(".af-bak").exists():
        shutil.move(world_f.with_suffix(".af-bak"), world_f)

    args = ["/apk.static", "--update-cache", "add", "--upgrade", "--latest"]
    rc, _ = cont.run(args, ro_root=False, net=True, bootstrap=True, **kwargs)

    for filename in bootstrap_files:
        if filename.with_suffix(".apk-new").exists():
            shutil.move(filename.with_suffix(".apk-new"), filename)
        elif subprocess.run(
                    [_APK_STATIC, "--root", cdir, "info",
                    "--who-owns", filename.relative_to(cdir)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                ).returncode != 0:
            filename.unlink()

    return rc

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
    # FIXME: maybe not needed as a separate file from /etc/apk/arch
    arch = cdir / "af/info/arch"
    if not arch.is_file():
        raise FileNotFoundError("/af/info/arch file is required")
    (cdir / "etc/apk").mkdir(parents=True, exist_ok=True)
    shutil.copy2(arch, cdir / "etc/apk/arch")
    arch = arch.read_text().strip()

    conf_d = cdir / "af/info/aportsdir/.apkfoundry" / branch

    for skel in (
            SITE_CONF / "skel",
            conf_d / "skel",
            conf_d / f"skel.{repo}",
            conf_d / f"skel..{arch}",
            conf_d / f"skel.{repo}.{arch}",
        ):

        if not skel.is_dir():
            continue

        _force_copytree(skel, cdir)
