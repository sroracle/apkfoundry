# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019-2020 Max Rees
# See LICENSE for more information.
import argparse   # ArgumentParser
import enum       # Enum, IntFlag, unique
import functools  # partial
import logging    # getLogger
import os         # access, *_OK
import re         # compile
import shutil     # chown, copy2, rmtree
import subprocess # check_output
import tempfile   # mkdtemp
import textwrap   # TextWrapper
from pathlib import Path

import apkfoundry           # DEFAULT_ARCH, LOCALSTATEDIR, MOUNTS, proj_conf
import apkfoundry.container # cont_make
import apkfoundry.digraph   # generate_graph
import apkfoundry._log as _log
import apkfoundry._util as _util

_LOGGER = logging.getLogger(__name__)

@enum.unique
class Status(enum.IntFlag):
    DONE = 8
    ERROR = DONE | 16      # 24
    CANCEL = ERROR | 32    # 56
    SUCCESS = DONE | 64    # 72
    FAIL = ERROR | 128     # 152
    DEPFAIL = CANCEL | 256 # 312

    # The following (and also CANCEL) are no longer used and may be
    # removed in a future version.
    NEW = 1
    REJECT = 2
    START = 4
    SKIP = DONE | 512      # 520

    def __str__(self):
        return self.name

class FailureAction(enum.Enum):
    STOP = 0
    RECALCULATE = 1
    IGNORE = 2

_REPORT_STATUSES = (
    Status.SUCCESS,
    Status.DEPFAIL,
    Status.FAIL,
    Status.ERROR,
    Status.CANCEL,
)
_NET_OPTION = re.compile(r"""^options=(["']?)[^"']*\bnet\b[^"']*\1""")
_wrap = textwrap.TextWrapper()

def _stats_list(status, l):
    if not l:
        return

    _LOGGER.info("%s: %d", status.name.title(), len(l))
    l = _wrap.fill(" ".join(l)).splitlines()
    for i in l:
        _log.msg2(_LOGGER, "%s", i)

def _stats_builds(done):
    _LOGGER.info("Total: %d", len(done))

    statuses = {
        status: [i for i in done if done[i] == status]
        for status in _REPORT_STATUSES
    }

    for status, startdirs in statuses.items():
        _stats_list(status, startdirs)

    for status in set(_REPORT_STATUSES) - {Status.SUCCESS}:
        if any(statuses[status]):
            return 1
    return 0

def run_task(cont, startdir, script):
    buildbase = Path(apkfoundry.MOUNTS["builddir"]) / startdir

    tmp_real = cont.cdir / "af/info/builddir" / startdir / "tmp"
    try:
        shutil.rmtree(tmp_real.parent)
    except (FileNotFoundError, PermissionError):
        pass
    tmp_real.mkdir(parents=True, exist_ok=True)
    tmp = str(buildbase / "tmp")

    env = {
        "HOME": tmp,
        "TEMP": tmp,
        "TEMPDIR": tmp,
        "TMP": tmp,
        "TMPDIR": tmp,

        "ABUILD_TMP": str(apkfoundry.MOUNTS["builddir"]),
        # "deps" is a waste of time since world will be refreshed
        # on next package
        "CLEANUP": "srcdir pkgdir",
        "ERROR_CLEANUP": "",
    }


    APKBUILD = cont.cdir / f"af/info/aportsdir/{startdir}/APKBUILD"
    net = False
    with open(APKBUILD) as f:
        for line in f:
            if _NET_OPTION.search(line) is not None:
                net = True
                break

    if net:
        _LOGGER.warning("%s: network access enabled", startdir)

    repo = startdir.split("/")[0]

    rc, _ = cont.run(
        [script, startdir],
        repo=repo,
        env=env,
        net=net,
    )

    if rc == 0:
        try:
            # Only remove TEMP files, not src/pkg
            _LOGGER.info("Removing package tmpfiles")
            shutil.rmtree(tmp_real)
        except (FileNotFoundError, PermissionError):
            pass

    return rc

def run_graph(cont, conf, graph, startdirs, script):
    initial = set(startdirs)
    done = {}

    try:
        on_failure = FailureAction[conf["on_failure"].upper()]
    except KeyError:
        _LOGGER.error(
            "on_failure = %s is invalid; defaulting to STOP",
            conf["on_failure"].upper(),
        )
        on_failure = FailureAction.STOP

    while True:
        order = [
            i for i in graph.topological_sort()
            if i in initial and i not in done
        ]
        if not order:
            break

        tot = len(order)
        cur = 0

        _log.section_start(_LOGGER, "build_order", "Build order:\n")
        for startdir in order:
            cur += 1
            _log.msg2(_LOGGER, "(%d/%d) %s", cur, tot, startdir)
        _log.section_end(_LOGGER)

        cur = 0
        for startdir in order:
            cur += 1
            _log.section_start(
                _LOGGER, "build_" + startdir.replace("/", "_"),
                "(%d/%d) Start: %s", cur, tot, startdir
            )

            rc = run_task(cont, startdir, script)

            if rc == 0:
                _log.section_end(
                    _LOGGER, "(%d/%d) Success: %s", cur, tot, startdir,
                )
                done[startdir] = Status.SUCCESS

            else:
                _log.section_end(
                    _LOGGER, "(%d/%d) Fail: %s", cur, tot, startdir,
                )
                done[startdir] = Status.FAIL

                if on_failure == FailureAction.RECALCULATE:
                    _log.section_start(
                        _LOGGER, "recalc-order", "Recalculating build order"
                    )

                    depfails = set(graph.all_downstreams(startdir))
                    for rdep in depfails:
                        graph.delete_node(rdep)
                    graph.delete_node(startdir)

                    depfails &= initial
                    for rdep in depfails:
                        _LOGGER.error("Depfail: %s", rdep)
                        done[rdep] = Status.DEPFAIL

                    _log.section_end(_LOGGER)

                elif on_failure == FailureAction.STOP:
                    _LOGGER.error("Stopping due to previous error")
                    cancels = initial - set(done.keys())
                    for rdep in cancels:
                        done[rdep] = Status.DEPFAIL
                    graph.reset_graph()

                elif on_failure == FailureAction.IGNORE:
                    _LOGGER.info("Ignoring error and continuing")

                break

    return _stats_builds(done)

def run_job(cont, conf, startdirs, script):
    _log.section_start(
        _LOGGER, "gen-build-order", "Generating build order...",
    )
    graph = apkfoundry.digraph.generate_graph(conf, cont=cont)
    if not graph or not graph.is_acyclic():
        _LOGGER.error("failed to generate dependency graph")
        return 1
    _log.section_end(_LOGGER)

    return run_graph(cont, conf, graph, startdirs, script)

def changed_pkgs(*rev_range, gitdir=None):
    gitdir = ["-C", str(gitdir)] if gitdir else []

    pkgs = subprocess.check_output(
        ("git", *gitdir, "diff-tree",
         "-r", "--name-only", "--diff-filter", "dxu",
         *rev_range, "--", "*/*/APKBUILD"),
        encoding="utf-8"
    ).splitlines()
    return [i.replace("/APKBUILD", "") for i in pkgs]

def resignapk(cdir, privkey, pubkey):
    repodir = cdir / "af/info/repodest"
    apks = list(repodir.glob("**/*.apk"))
    if not apks:
        return
    apks += list(repodir.glob("**/APKINDEX.tar.gz"))

    _log.section_start(_LOGGER, "resignapk", "Re-signing APKs...")
    _util.check_call((
        "fakeroot", "--",
        "resignapk", "-i",
        "-p", pubkey,
        "-k", privkey,
        *apks,
    ))
    _log.section_end(_LOGGER)

def _cleanup(rc, cont, delete):
    if hasattr(cont, "destroy"):
        destroy = cont.destroy
    else:
        destroy = functools.partial(shutil.rmtree, cont)

    if cont and (delete == "always" or (delete == "on-success" and rc == 0)):
        _LOGGER.info("Deleting container...")
        rc = max(destroy() or 0, rc)

    return rc

def _ensure_dir(name):
    ok = True

    if not name.is_dir():
        name.mkdir(parents=True)
        return ok

    if not os.access(name, os.R_OK | os.W_OK | os.X_OK):
        ok = False
        _LOGGER.critical(
            "%s is not accessible",
            name,
        )

    return ok

def _build_list(conf, opts):
    if opts.startdirs:
        _log.section_start(
            _LOGGER, "manual_pkgs",
            "The following packages were manually included:"
        )
        _log.msg2(_LOGGER, opts.startdirs)
        _log.section_end(_LOGGER)

    if opts.rev_range:
        _log.section_start(
            _LOGGER, "changed_pkgs", "Determining changed packages..."
        )
        pkgs = changed_pkgs(*opts.rev_range.split(), gitdir=opts.aportsdir)
        _log.msg2(_LOGGER, pkgs)
        _log.section_end(_LOGGER)
        opts.startdirs.extend(_filter_list(conf, opts, pkgs))

def _filter_list(conf, opts, startdirs):
    _log.section_start(
        _LOGGER, "skip_pkgs",
        "Determining packages to skip...",
    )

    repos = conf.getmaplist("repos")
    skip = conf.getmaplist("skip")
    for startdir in startdirs:
        # Already manually included
        if startdir in opts.startdirs:
            continue
        repo, _ = startdir.split("/", maxsplit=1)
        arches = repos.get(repo)
        if arches is None:
            _log.msg2(
                _LOGGER, "%s - repository not configured",
                startdir,
            )
            continue
        if opts.arch not in arches:
            _log.msg2(
                _LOGGER, "%s - repository not enabled for %s",
                startdir, opts.arch,
            )
            continue
        if opts.arch in skip.get(startdir, {}):
            _log.msg2(
                _LOGGER, "%s - package skipped for %s",
                startdir, opts.arch,
            )
            continue
        yield startdir

    _log.section_end(_LOGGER)

def _buildrepo_args(args):
    opts = argparse.ArgumentParser(
        usage="af-buildrepo [options ...] REPODEST STARTDIR [STARTDIR ...]",
    )

    cont = opts.add_argument_group(
        title="Container options",
    )
    cont.add_argument(
        "-A", "--arch",
        help=f"""APK architecture name (default:
        {apkfoundry.DEFAULT_ARCH})""",
    )
    cont.add_argument(
        "-c", "--cache",
        help="external APK cache directory (default: none)",
    )
    cont.add_argument(
        "--directory", metavar="CDIR",
        help=f"""use CDIR as the container root (default: temporary
        directory in {apkfoundry.LOCALSTATEDIR})""",
    )
    cont.add_argument(
        "-S", "--setarch",
        help="""setarch(8) architecture name (default: look in site
        configuration, otherwise none)""",
    )
    cont.add_argument(
        "-s", "--srcdest",
        help="external source file directory (default: none)",
    )

    checkout = opts.add_argument_group(
        title="Checkout options",
    )
    checkout.add_argument(
        "-a", "--aportsdir",
        help="project git directory",
    )
    checkout.add_argument(
        "-g", "--git-url",
        help="git repository URL",
    )
    checkout.add_argument(
        "--branch",
        help="""git branch for APORTSDIR (default: detect). This is
        useful when APORTSDIR is in a detached HEAD state.""",
    )

    opts.add_argument(
        "-D", "--delete", choices=("always", "on-success", "never"),
        default="never",
        help="when to delete the container (default: never)",
    )
    opts.add_argument(
        "--dry-run", action="store_true",
        help="only show what would be built, then exit",
    )
    opts.add_argument(
        "-k", "--key",
        help="re-sign APKs with FILE outside of container",
    )
    opts.add_argument(
        "--pubkey",
        help="""the filename to use for the KEY (to match /etc/apk/keys;
        default: KEY.pub)""",
    )
    opts.add_argument(
        "-r", "--rev-range",
        help="git revision range for changed APKBUILDs",
    )
    opts.add_argument(
        "--script",
        help="""Alternative build script to use instead of
        $AF_BRANCHDIR/build. Must be an absolute path underneath the
        container root.""",
    )
    opts.add_argument(
        "repodest", metavar="REPODEST",
        help="package destination directory",
    )
    opts.add_argument(
        "startdirs", metavar="STARTDIR", nargs="*",
        help="list of STARTDIRs to build",
    )
    return opts.parse_args(args)

def _buildrepo_bootstrap(opts, cdir):
    _log.section_start(
        _LOGGER, "bootstrap", "Bootstrapping container..."
    )
    cont_make_args = []
    if opts.repodest:
        cont_make_args += ["--repodest", opts.repodest]
        opts.repodest = Path(opts.repodest)
        if not _ensure_dir(opts.repodest):
            return None
    if opts.srcdest:
        cont_make_args += ["--srcdest", opts.srcdest]
        opts.srcdest = Path(opts.srcdest)
        if not _ensure_dir(opts.srcdest):
            return None
    if opts.cache:
        cont_make_args += ["--cache", opts.cache]
        opts.cache = Path(opts.cache)
        if not _ensure_dir(opts.cache):
            return None
    if opts.setarch:
        cont_make_args += ["--setarch", opts.setarch]

    cont_make_args += [
        "--arch", opts.arch,
        "--branch", opts.branch,
        "--", str(cdir), str(opts.aportsdir),
    ]
    cont = apkfoundry.container.cont_make(cont_make_args)
    _log.section_end(_LOGGER)
    return cont

def buildrepo(args):
    opts = _buildrepo_args(args)

    if not opts.arch:
        opts.arch = apkfoundry.DEFAULT_ARCH

    if not (opts.aportsdir or opts.git_url) \
            or (opts.aportsdir and opts.git_url):
        _LOGGER.error(
            "You must specify only one of -a APORTSDIR or -g GIT_URL"
        )
        return _cleanup(1, None, opts.delete)

    if opts.aportsdir:
        opts.aportsdir = Path(opts.aportsdir)
        if not opts.branch:
            opts.branch = _util.get_branch(opts.aportsdir)

    if opts.directory:
        cdir = Path(opts.directory)
    else:
        apkfoundry.LOCALSTATEDIR.mkdir(parents=True, exist_ok=True)
        cdir = Path(tempfile.mkdtemp(dir=apkfoundry.LOCALSTATEDIR, suffix=".af"))

    if opts.git_url:
        if not opts.branch:
            opts.branch = "master"

        _log.section_start(_LOGGER, "clone", "Cloning git repository...")
        opts.aportsdir = cdir / apkfoundry.MOUNTS["aportsdir"].lstrip("/")
        opts.aportsdir.mkdir(parents=True, exist_ok=True)
        _util.check_call((
            "git", "clone", opts.git_url, opts.aportsdir,
        ))
        _util.check_call((
            "git", "-C", opts.aportsdir,
            "checkout", opts.branch,
        ))
        if not (opts.aportsdir / ".apkfoundry").is_dir():
            _LOGGER.critical("No .apkfoundry configuration directory exists!")
            return _cleanup(1, cdir, opts.delete)
        _log.section_end(_LOGGER)

    branchdir = _util.get_branchdir(opts.aportsdir, opts.branch)
    conf = apkfoundry.proj_conf(opts.aportsdir, opts.branch)

    if not opts.script:
        opts.script = Path(apkfoundry.MOUNTS["aportsdir"]) \
            / ".apkfoundry" / branchdir.name / "build"

    _build_list(conf, opts)
    if not opts.startdirs:
        _LOGGER.info("No packages to build!")
        return _cleanup(0, cdir, opts.delete)

    if opts.dry_run:
        return _cleanup(0, cdir, "always")

    cont = _buildrepo_bootstrap(opts, cdir)
    if not cont:
        _LOGGER.error("Failed to bootstrap container")
        return _cleanup(1, cont, opts.delete)

    rc = run_job(cont, conf, opts.startdirs, opts.script)

    if opts.key:
        if opts.pubkey is None:
            opts.pubkey = Path(opts.key).name + ".pub"
        resignapk(cdir, opts.key, opts.pubkey)

    return _cleanup(rc, cont, opts.delete)
