# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019-2020 Max Rees
# See LICENSE for more information.
import argparse   # ArgumentParser
import json       # load
import logging    # getLogger
import os         # close, environ, fdopen, getgid, getuid, listdir, pipe, write
                  # isatty, tcgetpgrp, tcsetpgrp
import select     # select
import shutil     # chown, copy2, copytree, rmtree
import signal     # SIG_IGN, signal, SIGTTOU
import subprocess # call, Popen
import sys        # stdin
from pathlib import Path

import apkfoundry         # BWRAP, DEFAULT_ARCH, HOME, LIBEXECDIR, MOUNTS,
                          # ROOTFS_CACHE, SYSCONFDIR, proj_conf, site_conf
import apkfoundry._rootfs as _rootfs
import apkfoundry._sudo as _sudo
import apkfoundry._util as _util

_LOGGER = logging.getLogger(__name__)

_KEEP_ENV = (
    "TERM",
)
_SITE_CONF = apkfoundry.site_conf()
_SUBID = _SITE_CONF.getint("container", "subid")
_ABUILD_USERDIR = "af/config/abuild"

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

    if len(args) % 3 != 0:
        raise ValueError("map must have 3 entries per line")

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
        "sudo_conn",

        "_branch",
        "_branchdir",
        "_repo",
        "_arch",

        "_uid",
        "_gid",
    )

    def __init__(self, cdir, *, sudo=True):
        self.cdir = Path(cdir).resolve(strict=True)
        if sudo:
            self.sudo_conn = _sudo.client_init(self.cdir)
        else:
            self.sudo_conn = None

        self._branch = None
        self._branchdir = None
        self._repo = None
        self._arch = None

        self._uid = os.getuid()
        self._gid = os.getgid()

    def _read_info(self, name):
        f = self.cdir / name
        if f.is_file():
            return f.read_text().strip()
        return None

    @property
    def branch(self):
        if not self._branch:
            self._branch = self._read_info("af/config/branch")
        return self._branch

    @property
    def branchdir(self):
        if self.branch and not self._branchdir:
            self._branchdir = _util.get_branchdir(
                self.cdir / "af/config/aportsdir", self.branch
            )
        return self._branchdir

    @property
    def repo(self):
        if not self._repo:
            self._repo = self._read_info("af/config/repo")
        return self._repo

    @repo.setter
    def repo(self, value):
        self._repo = value
        (self.cdir / "af/config/repo").write_text(value.strip())

    @property
    def arch(self):
        if not self._arch:
            self._arch = self._read_info("etc/apk/arch")
        return self._arch

    def _bwrap(self, args, *, net=False, su=False, setsid=True, **kwargs):
        if "env" not in kwargs:
            kwargs["env"] = {}
        kwargs["env"].update({
            name: os.environ[name] for name in _KEEP_ENV \
            if name in os.environ and name not in kwargs["env"]
        })
        user = "root" if su else "build"
        kwargs["env"].update({
            "LOGNAME": user,
            "USER": user,
            "UID": str(0 if su else self._uid),
            "PATH": "/usr/bin:/usr/sbin:/bin:/sbin",
        })

        info_r, info_w = os.pipe()
        pipe_r, pipe_w = os.pipe()
        if "pass_fds" not in kwargs:
            kwargs["pass_fds"] = []
        kwargs["pass_fds"].extend((pipe_r, info_w))

        args_pre = [
            apkfoundry.BWRAP,
            "--die-with-parent",
            "--unshare-all",
            "--unshare-user",
            "--userns-block-fd", str(pipe_r),
            "--info-fd", str(info_w),
            "--uid", str(0 if su else self._uid),
            "--gid", str(0 if su else self._gid),
        ]

        if net:
            args_pre.append("--share-net")

        stdin = sys.stdin.fileno()
        if setsid:
            args_pre.append("--new-session")
            pgrp = None
        elif os.isatty(stdin):
            pgrp = os.tcgetpgrp(stdin)
        else:
            pgrp = None

        if su:
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

        if pgrp:
            handler = signal.signal(signal.SIGTTOU, signal.SIG_IGN)
            os.tcsetpgrp(stdin, pgrp)
            signal.signal(signal.SIGTTOU, handler)

        retcodes.append(proc.returncode)
        success = all(i == 0 for i in retcodes)
        if not success:
            _LOGGER.debug("container failed with status %r!", retcodes)
        return (max(abs(i) for i in retcodes), proc)

    def _resolv_mounts(self):
        mounts = apkfoundry.MOUNTS.copy()
        for mount in mounts:
            mounts[mount] = self.cdir / "af/config" / mount
            if not mounts[mount].is_symlink():
                raise RuntimeError(f"af/config/{mount} isn't a symlink")
            mounts[mount] = mounts[mount].resolve(strict=True)
        return mounts

    def _run_env(self, kwargs):
        if self.branchdir:
            branchdir = Path(apkfoundry.MOUNTS["aportsdir"]) / ".apkfoundry"
            branchdir /= self.branchdir.name
        else:
            branchdir = ""

        if "env" not in kwargs:
            kwargs["env"] = {}
        kwargs["env"].update({
            "SRCDEST": apkfoundry.MOUNTS["srcdest"],
            "APORTSDIR": apkfoundry.MOUNTS["aportsdir"],
            "REPODEST": apkfoundry.MOUNTS["repodest"],
            "ABUILD_USERDIR": "/" + _ABUILD_USERDIR,
            "ABUILD_USERCONF": "/" + _ABUILD_USERDIR + "/abuild.conf",
            "ABUILD_GIT": "git -C " + apkfoundry.MOUNTS["aportsdir"],

            "AF_BUILD_UID": str(self._uid),
            "AF_BUILD_GID": str(self._gid),

            "AF_BRANCH": self.branch or "",
            "AF_BRANCHDIR": branchdir,
            "AF_REPO": self.repo or "",
            "AF_ARCH": self.arch or "",

            "AF_LIBEXEC": "/af/libexec",
        })

    def run_external(self, cmd, skip_mounts=False, **kwargs):
        args = [
            "--ro-bind", "/", "/",
            "--dev-bind", "/dev", "/dev",
            "--proc", "/proc",
            "--tmpfs", "/tmp",
            "--tmpfs", "/var/tmp",
            "--dir", "/tmp/af",
            "--dir", "/tmp/af/rootfs-cache",
            "--dir", "/tmp/af/libexec",
            "--dir", "/tmp/af/cdir",
            "--ro-bind", apkfoundry.LIBEXECDIR, "/tmp/af/libexec",
            "--ro-bind-try", apkfoundry.ROOTFS_CACHE, "/tmp/af/rootfs-cache",
            "--bind", self.cdir, "/tmp/af/cdir",
        ]

        if not skip_mounts:
            mounts = self._resolv_mounts()
            args += [
                "--bind", mounts["aportsdir"],
                "/tmp/af/cdir" + apkfoundry.MOUNTS["aportsdir"],
                "--bind", mounts["repodest"],
                "/tmp/af/cdir" + apkfoundry.MOUNTS["repodest"],
                "--bind", mounts["srcdest"],
                "/tmp/af/cdir" + apkfoundry.MOUNTS["srcdest"],
                "--bind", mounts["builddir"],
                "/tmp/af/cdir" + apkfoundry.MOUNTS["builddir"],
            ]

            # TODO: mount cache?

            if self.branchdir:
                args += [
                    "--bind", self.branchdir,
                    "/tmp/af/branchdir",
                ]

        args += [
            "--tmpfs", apkfoundry.HOME,
            "--chdir", "/tmp/af/cdir",
            "/tmp/af/libexec/af-su",
            *cmd,
        ]
        return self._bwrap(args, **kwargs, su=True)

    def bootstrap(self, conf, arch, script, **kwargs):
        self._arch = arch

        rc = _rootfs.extract_rootfs(self, conf)
        if rc:
            return rc

        userdir_template = apkfoundry.SYSCONFDIR / "abuild"
        userdir_cdir = self.cdir / _ABUILD_USERDIR
        if userdir_template.is_dir():
            shutil.copytree(userdir_template, userdir_cdir)
        else:
            userdir_cdir.mkdir(parents=True)

        rc, _ = self.run(
            (script,),
            su=True, net=True, ro_root=False, skip_refresh=True,
            **kwargs,
        )
        return rc

    def destroy(self):
        children = os.listdir(self.cdir)
        if children:
            rc, _ = self.run_external(
                # Relative to CWD = cdir
                ("rm", "-rf", *children),
                skip_mounts=True,
            )
            if rc:
                return rc
        self.cdir.rmdir()
        return 0

    def refresh(self, setsid=False):
        script = self.branchdir / "refresh"
        if not script.is_file():
            _LOGGER.warning("No refresh script found")
            return 0
        script = script.relative_to(self.branchdir.parent.parent)
        script = Path(apkfoundry.MOUNTS["aportsdir"]) / script

        rc, _ = self.run(
            (str(script),),
            setsid=setsid, skip_refresh=True,
            su=True, net=True, ro_root=False,
        )
        return rc

    def run(self,
            cmd,
            *,
            repo=None,
            ro_aports=True,
            ro_root=True,
            skip_mounts=False,
            skip_refresh=False,
            skip_sudo=False,

            net=False,
            setsid=True,
            chdir=None,
            **kwargs):

        root_bind = "--ro-bind" if ro_root else "--bind"
        aports_bind = "--ro-bind" if ro_aports else "--bind"

        self._run_env(kwargs)

        args = [
            root_bind, self.cdir, "/",
            "--dev-bind", "/dev", "/dev",
            "--proc", "/proc",
            "--ro-bind", str(apkfoundry.LIBEXECDIR), "/af/libexec",
            "--ro-bind", self.cdir / "af/config", "/af/config",
            "--bind", self.cdir / _ABUILD_USERDIR, "/af/config/abuild",
            "--bind", self.cdir / "af/config/host", "/af/config/host",
            "--ro-bind", "/etc/hosts", "/af/config/host/hosts",
            "--ro-bind", "/etc/resolv.conf", "/af/config/host/resolv.conf",
            "--ro-bind-try", self.cdir / "af/scripts", "/af/scripts",
        ]

        if not skip_mounts:
            mounts = self._resolv_mounts()
            args += [
                "--bind", self.cdir / "tmp", "/tmp",
                "--bind", self.cdir / "var/tmp", "/var/tmp",
                aports_bind, mounts["aportsdir"], apkfoundry.MOUNTS["aportsdir"],
                "--bind", mounts["repodest"], apkfoundry.MOUNTS["repodest"],
                "--bind", mounts["srcdest"], apkfoundry.MOUNTS["srcdest"],
                "--bind", mounts["builddir"], apkfoundry.MOUNTS["builddir"],
                "--chdir", chdir or apkfoundry.MOUNTS["aportsdir"],
            ]
            if (self.cdir / "af/config/cache").exists():
                args += [
                    "--bind", self.cdir / "af/config/cache", "/etc/apk/cache",
                ]
            if repo:
                self.repo = repo

        if not skip_refresh and self.refresh():
            return 1, None

        if self.sudo_conn and not skip_sudo:
            if "pass_fds" not in kwargs:
                kwargs["pass_fds"] = []
            kwargs["pass_fds"].append(self.sudo_conn.fileno())
            kwargs["env"].update({
                "AF_SUDO_FD": str(self.sudo_conn.fileno()),
                "ABUILD_FETCH": "/af/libexec/af-sudo abuild-fetch",
                "ADDGROUP": "/af/libexec/af-sudo abuild-addgroup",
                "ADDUSER": "/af/libexec/af-sudo abuild-adduser",
                "SUDO_APK": "/af/libexec/af-sudo abuild-apk",
                "APK_FETCH": "/af/libexec/af-sudo apk",
            })
        else:
            kwargs["env"].update({
                "ABUILD_FETCH": "abuild-fetch",
                "ADDGROUP": "abuild-addgroup",
                "ADDUSER": "abuild-adduser",
                "SUDO_APK": "abuild-apk",
                "APK_FETCH": "apk",
            })

        setarch_f = self.cdir / "af/config/setarch"
        if setarch_f.is_file():
            args.extend(["setarch", setarch_f.read_text().strip()])

        if kwargs.get("su", False):
            args.append("/af/libexec/af-su")

        args.extend(cmd)
        return self._bwrap(
            args,
            net=net,
            setsid=setsid,
            **kwargs,
        )

def _make_infodir(conf, opts):
    af_info = opts.cdir / "af/config/host"
    af_info.mkdir(parents=True)
    af_info = af_info.parent

    (af_info / "branch").write_text(opts.branch.strip())
    (af_info / "repo").write_text(conf["default_repo"].strip())

    if opts.setarch:
        (opts.cdir / "af/config/setarch").write_text(opts.setarch.strip())

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

        (opts.cdir / "af/config" / mount).symlink_to(mounts[mount])

    for mount in apkfoundry.MOUNTS:
        if mounts.get(mount):
            continue

        (opts.cdir / "af/config" / mount).symlink_to(
            opts.cdir / apkfoundry.MOUNTS[mount].lstrip("/")
        )

    (opts.cdir / "af/libexec").mkdir()

    if opts.cache:
        (opts.cdir / "af/config/cache").symlink_to(opts.cache)

def _cont_make_args(args):
    opts = argparse.ArgumentParser(
        usage="af-mkchroot [options ...] CDIR APORTSDIR",
        description="""Make a new APK Foundry container."""
    )
    opts.add_argument(
        "-A", "--arch",
        help=f"""APK architecture name (default:
        {apkfoundry.DEFAULT_ARCH})""",
    )
    opts.add_argument(
        "--branch",
        help="""git branch for APORTSDIR (default: detect). This is
        useful when APORTSDIR is in a detached HEAD state.""",
    )
    opts.add_argument(
        "-c", "--cache",
        help="external APK cache directory (default: none)",
    )
    opts.add_argument(
        "--no-pubkey-copy", action="store_true",
        help="do not copy public keys to REPODEST",
    )
    opts.add_argument(
        "-r", "--repodest",
        help="""external package destination directory (default:
        none)""",
    )
    opts.add_argument(
        "-S", "--setarch",
        help="""setarch(8) architecture name (default: look in site
        configuration, otherwise none)""",
    )
    opts.add_argument(
        "-s", "--srcdest",
        help="external source file directory (default: none)",
    )
    opts.add_argument(
        "cdir", metavar="CDIR",
        help="container directory",
    )
    opts.add_argument(
        "aportsdir", metavar="APORTSDIR",
        help="project git directory",
    )
    return opts.parse_args(args)

def cont_make(args):
    opts = _cont_make_args(args)
    opts.cdir = Path(opts.cdir)

    if not opts.arch:
        opts.arch = apkfoundry.DEFAULT_ARCH
    if not opts.setarch:
        opts.setarch = _SITE_CONF.get("setarch", opts.arch, fallback=None)
    if not opts.branch:
        opts.branch = _util.get_branch(opts.aportsdir)
    branchdir = _util.get_branchdir(opts.aportsdir, opts.branch)
    conf = apkfoundry.proj_conf(opts.aportsdir, opts.branch)

    (opts.cdir / "af").mkdir(parents=True, exist_ok=True)
    opts.cdir.chmod(0o770)

    script = branchdir / "bootstrap"
    if not script.is_file():
        _LOGGER.error("missing bootstrap script")
        return None
    script = Path(apkfoundry.MOUNTS["aportsdir"]) \
        / ".apkfoundry" / script.relative_to(branchdir.parent)

    for mount in apkfoundry.MOUNTS.values():
        (opts.cdir / mount.lstrip("/")).mkdir(parents=True, exist_ok=True)

    _make_infodir(conf, opts)

    cont = Container(opts.cdir)
    rc = cont.bootstrap(
        conf, opts.arch, script,
        env={
            "AF_PUBKEY_COPY": "" if opts.no_pubkey_copy else "Yes",
        },
    )
    if rc:
        return None

    return cont
