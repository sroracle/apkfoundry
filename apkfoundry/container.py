# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019-2020 Max Rees
# See LICENSE for more information.
import argparse   # ArgumentParser
import json       # load
import logging    # getLogger
import os         # close, environ, fdopen, getgid, getuid, pipe, write
import select     # select
import shutil     # chown, copy2, rmtree
import subprocess # call, Popen
from pathlib import Path

import apkfoundry         # BWRAP, DEFAULT_ARCH, LIBEXECDIR, LOCALSTATEDIR,
                          # MOUNTS, SYSCONFDIR, local_conf, site_conf
import apkfoundry._root as _root
import apkfoundry._util as _util

_LOGGER = logging.getLogger(__name__)

_KEEP_ENV = (
    "TERM",
)
_SUBID = apkfoundry.site_conf().getint("container", "subid")

def _idmap(cmd, pid, ent_id):
    holes = {
        0: _SUBID,
        ent_id: ent_id,
    }

    args = []
    for mapped, real in holes.items():
        args += [mapped, real, 1]

    gaps = list(holes.keys())
    gaps = list(zip(gaps[:-1], gaps[1:]))
    gaps.append((max(holes.keys()), 65536))

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

class Container:
    __slots__ = (
        "cdir",
        "rootd_conn",

        "_uid",
        "_gid",
    )

    def __init__(self, cdir, *, rootd=True):
        self.cdir = Path(cdir)
        if not self.cdir.exists():
            raise FileNotFoundError(f"'{self.cdir}' does not exist")

        self._uid = os.getuid()
        self._gid = os.getgid()

        if rootd:
            self.rootd_conn = _root.client_init(self.cdir)
        else:
            self.rootd_conn = None

    def _bwrap(self, args, *, net=False, root=False, setsid=True, **kwargs):
        if "env" not in kwargs:
            kwargs["env"] = {}
        kwargs["env"].update({
            name: os.environ[name] for name in _KEEP_ENV \
            if name in os.environ and name not in kwargs["env"]
        })
        user = "root" if root else "build"
        kwargs["env"].update({
            "LOGNAME": user,
            "USER": user,
            "UID": str(0 if root else self._uid),
            "PATH": "/usr/bin:/usr/sbin:/bin:/sbin",
        })

        info_r, info_w = os.pipe()
        pipe_r, pipe_w = os.pipe()
        if "pass_fds" not in kwargs:
            kwargs["pass_fds"] = []
        kwargs["pass_fds"].extend((pipe_r, info_w))

        args_pre = [
            apkfoundry.BWRAP,
            "--unshare-all",
            "--unshare-user",
            "--userns-block-fd", str(pipe_r),
            "--info-fd", str(info_w),
            "--uid", str(0 if root else self._uid),
            "--gid", str(0 if root else self._gid),
        ]

        if net:
            args_pre.append("--share-net")
        if setsid:
            args_pre.append("--new-session")

        if root:
            args_pre.extend([
                "--cap-add", "CAP_CHOWN",
                "--cap-add", "CAP_FOWNER",
                "--cap-add", "CAP_DAC_OVERRIDE",
                # Required to restore security file caps during package
                # installation. On Linux 4.14+ these caps are tied to
                # the user namespace in which they are created, but
                # fakeroot will handle this correctly
                "--cap-add", "CAP_SETFCAP",
                # Used by apk_db_run_script
                "--cap-add", "CAP_SYS_CHROOT",
                # Switch users (needed by af-su and bootstrap stage 2)
                "--cap-add", "CAP_SETUID",
                "--cap-add", "CAP_SETGID",
            ])

        proc = subprocess.Popen(args_pre + args, **kwargs)
        os.close(pipe_r)
        os.close(info_w)
        select.select([info_r], [], [])
        info = json.load(os.fdopen(info_r))
        retcodes = _userns_init(
            info["child-pid"], self._uid, self._gid,
        )
        os.write(pipe_w, b"\n")
        os.close(pipe_w)

        proc.stdout, proc.stderr = proc.communicate()
        retcodes.append(proc.returncode)
        success = all(i == 0 for i in retcodes)
        if not success:
            _LOGGER.debug("container failed with status %r!", retcodes)
        return (max(abs(i) for i in retcodes), proc)

    @staticmethod
    def _run_env(kwargs):
        if "env" not in kwargs:
            kwargs["env"] = {}
        kwargs["env"].update({
            "PACKAGER": "APK Foundry",
            "SRCDEST": apkfoundry.MOUNTS["srcdest"],
            "APORTSDIR": apkfoundry.MOUNTS["aportsdir"],
            "REPODEST": apkfoundry.MOUNTS["repodest"],
            "ABUILD_USERDIR": "/af/key",
            "ABUILD_GIT": "git -C " + apkfoundry.MOUNTS["aportsdir"],
            "ABUILD_FETCH": "/af/libexec/af-req-root abuild-fetch",
            "ADDGROUP": "/af/libexec/af-req-root abuild-addgroup",
            "ADDUSER": "/af/libexec/af-req-root abuild-adduser",
            "SUDO_APK": "/af/libexec/af-req-root abuild-apk",
            "APK_FETCH": "/af/libexec/af-req-root apk",
        })

    def run_external(self, cmd, **kwargs):
        args = [
            "--bind", "/", "/",
            "--chdir", self.cdir,
            apkfoundry.LIBEXECDIR / "af-su",
            *cmd,
        ]
        return self._bwrap(args, **kwargs, root=True)

    def bootstrap(self, arch):
        rc, _ = self.run_external(
            (self.cdir / "af/bootstrap-stage1",),
            net=True,
            env={
                "AF_ARCH": arch,
                "AF_ROOTFS_CACHE": apkfoundry.LOCALSTATEDIR / "rootfs-cache",
                "AF_SYSCONFDIR": apkfoundry.SYSCONFDIR,
            },
        )
        if rc:
            return rc

        rc = self.refresh()
        if rc:
            return rc

        rc, _ = self.run(
            ("/af/bootstrap-stage2",),
            root=True, net=True, ro_root=False,
            env={
                "AF_BUILD_UID": str(os.getuid()),
                "AF_BUILD_GID": str(os.getgid()),
            },
        )
        return rc

    def destroy(self):
        args = [
            "--bind", "/", "/",
            apkfoundry.LIBEXECDIR / "af-su",
            "rm", "-rf", self.cdir,
        ]
        return self._bwrap(args, root=True)

    def refresh(self, setsid=False):
        branch = (self.cdir / "af/info/branch").read_text().strip()
        branchdir = _util.get_branchdir(
            self.cdir / "af/info/aportsdir", branch
        )

        script = branchdir / "refresh"
        if not script.is_file():
            _LOGGER.warning("No refresh script found")
            return 0

        rc, _ = self.run_external(
            (script,),
            setsid=setsid, net=True,
            env={
                "AF_SYSCONFDIR": apkfoundry.SYSCONFDIR,
            },
        )
        return rc

    def run(self,
            cmd,
            *,
            repo=None,
            ro_aports=True,
            ro_root=True,
            skip_rootd=False,
            skip_mounts=False,

            net=False,
            setsid=True,
            **kwargs):

        root_bind = "--ro-bind" if ro_root else "--bind"
        aports_bind = "--ro-bind" if ro_aports else "--bind"

        self._run_env(kwargs)

        args = [
            root_bind, self.cdir, "/",
            "--dev-bind", "/dev", "/dev",
            "--proc", "/proc",
            "--ro-bind", str(apkfoundry.LIBEXECDIR), "/af/libexec",
        ]

        if not skip_mounts:
            mounts = apkfoundry.MOUNTS.copy()
            for mount in mounts:
                mounts[mount] = self.cdir / "af/info" / mount
                if not mounts[mount].is_symlink():
                    raise FileNotFoundError(mounts[mount])
            args += [
                "--bind", self.cdir / "tmp", "/tmp",
                "--bind", self.cdir / "var/tmp", "/var/tmp",
                aports_bind, mounts["aportsdir"], apkfoundry.MOUNTS["aportsdir"],
                "--bind", mounts["repodest"], apkfoundry.MOUNTS["repodest"],
                "--bind", mounts["srcdest"], apkfoundry.MOUNTS["srcdest"],
                "--bind", mounts["builddir"], apkfoundry.MOUNTS["builddir"],
                "--chdir", apkfoundry.MOUNTS["aportsdir"],
            ]
            if (self.cdir / "af/info/cache").exists():
                args += [
                    "--bind", self.cdir / "af/info/cache", "/etc/apk/cache",
                ]
            if repo:
                (self.cdir / "af/info/repo").write_text(repo.strip())

        if self.rootd_conn and not skip_rootd:
            if self.refresh():
                return 1, None
            if "pass_fds" not in kwargs:
                kwargs["pass_fds"] = []
            kwargs["pass_fds"].append(self.rootd_conn.fileno())
            args.extend((
                "--setenv", "AF_ROOT_FD", str(self.rootd_conn.fileno()),
            ))

        setarch_f = self.cdir / "af/info/setarch"
        if setarch_f.is_file() and not skip_mounts:
            args.extend(["setarch", setarch_f.read_text().strip()])

        if kwargs.get("root", False):
            args.append("/af/libexec/af-su")

        args.extend(cmd)
        return self._bwrap(
            args,
            net=net,
            setsid=setsid,
            **kwargs,
        )

def _make_infodir(conf, opts):
    af_info = opts.cdir / "af/info"
    af_info.mkdir()

    (af_info / "branch").write_text(opts.branch.strip())
    (af_info / "repo").write_text(conf["default_repo"].strip())

    if opts.setarch:
        (opts.cdir / "af/info/setarch").write_text(opts.setarch.strip())

    mounts = {
        "aportsdir": opts.aportsdir, # this make act weird since
                                     # it's always specified
        "repodest": opts.repodest,
        "srcdest": opts.srcdest,
    }

    for mount in mounts:
        if mount not in apkfoundry.MOUNTS:
            raise ValueError(f"Unknown mount '{mount}'")
        if not mounts[mount]:
            continue

        (opts.cdir / "af/info" / mount).symlink_to(mounts[mount])

    for mount in apkfoundry.MOUNTS:
        if mount in mounts and mounts[mount]:
            continue

        (opts.cdir / "af/info" / mount).symlink_to(
            opts.cdir / apkfoundry.MOUNTS[mount].lstrip("/")
        )

    (opts.cdir / "af/libexec").mkdir()

    if opts.cache:
        (opts.cdir / "af/info/cache").symlink_to(opts.cache)

def _cont_make_args(args):
    opts = argparse.ArgumentParser(
        usage="af-mkchroot [options ...] DIR APORTSDIR",
    )
    opts.add_argument(
        "-A", "--arch",
        help="APK architecture name (default: output of apk --print-arch)",
    )
    opts.add_argument(
        "--branch",
        help="""git branch for APORTSDIR (default: detect). This is
        useful when APORTSDIR is in a detached HEAD state.""",
    )
    opts.add_argument(
        "-c", "--cache",
        help="shared APK cache directory (default: disabled)",
    )
    opts.add_argument(
        "-r", "--repodest",
        help="""package destination directory (default: container root
        /af/repos)""",
    )
    opts.add_argument(
        "-S", "--setarch",
        help="setarch(8) architecture name (default: none)",
    )
    opts.add_argument(
        "-s", "--srcdest",
        help="""source file directory (default: container root
        /af/distfiles)""",
    )
    opts.add_argument(
        "cdir", metavar="DIR",
        help="container directory",
    )
    opts.add_argument(
        "aportsdir", metavar="APORTSDIR",
        help="project checkout directory",
    )
    return opts.parse_args(args)

def cont_make(args):
    opts = _cont_make_args(args)
    opts.cdir = Path(opts.cdir)

    if not opts.arch:
        opts.arch = apkfoundry.DEFAULT_ARCH
    if not opts.branch:
        opts.branch = _util.get_branch(opts.aportsdir)
    branchdir = _util.get_branchdir(opts.aportsdir, opts.branch)
    conf = apkfoundry.local_conf(opts.aportsdir, opts.branch)

    (opts.cdir / "af").mkdir(parents=True, exist_ok=True)
    opts.cdir.chmod(0o770)

    script1 = branchdir / "bootstrap-stage1"
    script2 = branchdir / "bootstrap-stage2"
    if not (script1.is_file() and script2.is_file()):
        _LOGGER.error("missing bootstrap scripts")
        return None
    shutil.copy2(script1, opts.cdir / "af")
    shutil.copy2(script2, opts.cdir / "af")

    for mount in apkfoundry.MOUNTS.values():
        (opts.cdir / mount.lstrip("/")).mkdir(parents=True, exist_ok=True)

    _make_infodir(conf, opts)

    cont = Container(opts.cdir)
    rc = cont.bootstrap(opts.arch)
    if rc:
        return None

    (opts.cdir / "af/bootstrap-stage1").unlink()
    (opts.cdir / "af/bootstrap-stage2").unlink()

    return cont
