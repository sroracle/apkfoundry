# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019-2020 Max Rees
# See LICENSE for more information.
import getpass    # getuser
import grp        # getgrnam
import json       # load
import logging    # getLogger
import os         # close, environ, getuid, getgid, pipe, walk, write
import pwd        # getpwuid
import select     # select
import shutil     # chown, copy2, copytree
import subprocess # call, Popen
from pathlib import Path

from . import get_config, LIBEXEC, SITE_CONF, rootid
from .socket import client_refresh

BUILDDIR = "/af/build"
MOUNTS = {
    "aportsdir": "/af/aports",
    "repodest": "/af/repos",
    "srcdest": "/var/cache/distfiles",
}

_LOGGER = logging.getLogger(__name__)

_KEEP_ENV = (
    "TERM",
)

_APK_STATIC = SITE_CONF / "skel.bootstrap/apk.static"
_CFG = get_config("container")
_SUBID = _CFG.getint("subid")

def _idmap(cmd, pid, id):
    if cmd == "newuidmap":
        holes = {
            0: rootid().pw_uid,
            id: id,
        }
    else:
        af_gid = grp.getgrnam("apkfoundry").gr_gid
        holes = {
            0: rootid().pw_gid,
            id: id,
            af_gid: af_gid,
        }

    assert holes[0] != id, "root ID cannot match user ID"

    args = []
    for mapped, real in holes.items():
        args += [mapped, real, 1]

    gaps = list(holes.keys())
    gaps = list(zip(gaps[:-1], gaps[1:]))
    gaps.append((max(holes.keys()), 65535))

    for map0, map1 in gaps:
        if not map0 - map1 or not map1 - (map0 + 1):
            continue
        args += [map0 + 1, _SUBID + map0 + 1, map1 - (map0 + 1)]

    assert len(args) % 3 == 0, "map must have 3 entries per line"

    args = [str(i) for i in args]
    return subprocess.call((cmd, str(pid), *args))

def _userns_init(pid, uid, gid):
    retcodes = []

    retcodes.append(_idmap("newuidmap", pid, uid))
    if retcodes[-1] != 0:
        return retcodes

    retcodes.append(_idmap("newgidmap", pid, gid))
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

        cdir_uid = self.cdir.stat().st_uid
        if self._owneruid != cdir_uid:
            if self._owneruid != rootid().pw_uid:
                raise PermissionError(f"'{self.cdir}' belongs to '{cdir_uid}'")

            self._owneruid = cdir_uid
            self._ownergid = pwd.getpwuid(self._owneruid).pw_gid
            self._setuid = self._setgid = 0

        self.rootd_conn = rootd_conn

    def run(self,
            cmd,
            *,
            bootstrap=False,
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
            "PACKAGER": "APK Foundry",
            "PATH": "/usr/bin:/usr/sbin:/bin:/sbin",
            "SRCDEST": MOUNTS["srcdest"],
            "APORTSDIR": MOUNTS["aportsdir"],
            "REPODEST": MOUNTS["repodest"],
            "ABUILD_USERDIR": "/af/key",
            "ABUILD_GIT": "git -C /af/aports",
            "ABUILD_FETCH": "/af/libexec/af-req-root abuild-fetch",
            "ADDGROUP": "/af/libexec/af-req-root abuild-addgroup",
            "ADDUSER": "/af/libexec/af-req-root abuild-adduser",
            "SUDO_APK": "/af/libexec/af-req-root abuild-apk",
            "APK_FETCH": "/af/libexec/af-req-root apk",
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
            "--bind", mounts["repodest"], MOUNTS["repodest"],
            "--bind", mounts["srcdest"], MOUNTS["srcdest"],
            "--bind", self.cdir / BUILDDIR.lstrip("/"), BUILDDIR,
            "--ro-bind", str(LIBEXEC), "/af/libexec",
            "--chdir", MOUNTS["aportsdir"],
        ]

        if repo:
            (self.cdir / "af/info/repo").write_text(repo.strip())

        if (self.cdir / "af/info/cache").exists():
            args.extend((
                "--bind", self.cdir / "af/info/cache", "/etc/apk/cache",
            ))

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

        if not net:
            args.append("--unshare-net")

        if self._setuid == 0:
            args.extend([
                "--cap-add", "CAP_CHOWN",
                "--cap-add", "CAP_FOWNER",
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

        if not success:
            _LOGGER.debug("container failed with status %r!", retcodes)

        return (max(abs(i) for i in retcodes), proc)

def cont_make(
        cdir,
        repo,
        *,
        arch=None,
        setarch=None,
        mounts=None,
        cache=None):

    cdir = Path(cdir)
    (cdir / "af").mkdir(parents=True, exist_ok=True)
    shutil.chown(cdir, group="apkfoundry")
    cdir.chmod(0o770)

    for mount in MOUNTS.values():
        (cdir / mount.lstrip("/")).mkdir(parents=True, exist_ok=True)

    if arch is None:
        arch = subprocess.check_output(
            [_APK_STATIC, "--print-arch"],
            encoding="utf-8",
        )
    (cdir / "etc/apk/keys").mkdir(parents=True, exist_ok=True)
    (cdir / "etc/apk/arch").write_text(arch.strip() + "\n")

    keydir = cdir / "af/key"
    env = os.environ.copy()
    env["ABUILD_USERDIR"] = str(keydir)
    subprocess.check_call(["abuild-keygen", "-anq"], env=env)

    privkey = (keydir / "abuild.conf").read_text().strip()
    privkey = privkey.replace("PACKAGER_PRIVKEY=\"", "", 1).rstrip("\"")
    pubkey = privkey + ".pub"
    shutil.copy2(pubkey, cdir / "etc/apk/keys")
    privkey = Path(privkey).relative_to(cdir)
    (keydir / "abuild.conf").write_text(f"PACKAGER_PRIVKEY=\"/{privkey}\"\n")

    for i in ("etc", "var"):
        for dirpath, _, filenames in os.walk(cdir / i):
            dirpath = Path(dirpath)
            dirpath.chmod(0o775)
            shutil.chown(dirpath, group="apkfoundry")
            for filename in filenames:
                (dirpath / filename).chmod(0o664)
                shutil.chown(dirpath / filename, group="apkfoundry")

    (cdir / BUILDDIR.lstrip("/")).mkdir(parents=True, exist_ok=True)

    af_info = cdir / "af/info"
    af_info.mkdir()

    for i in ("af", "af/info"):
        (cdir / i).chmod(0o755)
        shutil.chown(cdir / i, group="apkfoundry")

    (af_info / "repo").write_text(repo.strip())

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
        if mount in mounts and mounts[mount]:
            continue

        (cdir / "af/info" / mount).symlink_to(
            cdir / MOUNTS[mount].lstrip("/")
        )

    (cdir / "af/libexec").mkdir()

    if cache:
        (cdir / "af/info/cache").symlink_to(cache)

def cont_bootstrap(cdir, **kwargs):
    cont = Container(cdir)
    bootstrap_files = _force_copytree(SITE_CONF / "skel.bootstrap", cdir)

    (cdir / "dev").mkdir(exist_ok=True)
    (cdir / "tmp").mkdir(exist_ok=True)
    (cdir / "var/tmp").mkdir(exist_ok=True, parents=True)
    (cdir / "tmp").chmod(0o1777)
    (cdir / "var/tmp").chmod(0o1777)

    if (cdir / "af/info/cache").exists():
        (cdir / "etc/apk/cache").mkdir(parents=True, exist_ok=True)

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
        elif subprocess.call(
                    [
                        _APK_STATIC, "--root", cdir, "info",
                        "--who-owns", filename.relative_to(cdir)
                    ],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                ) != 0:
            filename.unlink()

    if rc != 0:
        return rc

    return rc

def cont_refresh(cdir):
    cdir = Path(cdir)

    repo = cdir / "af/info/repo"
    if not repo.is_file():
        raise FileNotFoundError("/af/info/repo file is required")
    repo = repo.read_text().strip()

    conf_d = cdir / "af/info/aportsdir/.apkfoundry"
    arch = (cdir / "etc/apk/arch").read_text().strip()

    for skel in (
            SITE_CONF / "skel",
            conf_d / "skel",
            conf_d / f"skel.{repo}",
            conf_d / f"skel..{arch}",
            conf_d / f"skel.{repo}.{arch}",
        ):

        if not skel.is_dir():
            _LOGGER.debug("could not find %s", skel)
            continue

        _force_copytree(skel, cdir)

    abuild_conf = SITE_CONF / "abuild.conf"
    if abuild_conf.is_file():
        shutil.copy2(abuild_conf, cdir / "etc/abuild.conf")
