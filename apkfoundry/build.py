# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019-2020 Max Rees
# See LICENSE for more information.
import argparse   # ArgumentParser, FileType
import enum       # Enum, IntFlag, unique
import logging    # getLogger
import re         # compile
import shutil     # chown, copy2, rmtree
import stat       # S_IMODE
import subprocess # check_output
import tempfile   # mkdtemp
import textwrap   # TextWrapper
from pathlib import Path

import apkfoundry           # MOUNTS, local_conf, msg2, section_end,
                            # section_start
import apkfoundry.container # Container, cont_make
import apkfoundry.digraph   # generate_graph
import apkfoundry.socket    # client_init
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

def run_task(cont, startdir):
    buildbase = apkfoundry.MOUNTS["builddir"] / startdir

    tmp_real = cont.cdir / str(buildbase).lstrip("/") / "tmp"
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

        "ABUILD_SRCDIR": str(buildbase / "src"),
        "ABUILD_PKGBASEDIR": str(buildbase / "pkg"),
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

    build_script = "/af/build-script.alt"
    if not (cont.cdir / build_script.lstrip("/")).is_file():
        build_script = "/af/build-script"

    rc, _ = cont.run(
        [build_script, startdir],
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

def run_graph(cont, conf, graph, startdirs):
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

            rc = run_task(cont, startdir)

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

def run_job(cont, conf, startdirs):
    _log.section_start(
        _LOGGER, "gen-build-order", "Generating build order...",
    )
    graph = apkfoundry.digraph.generate_graph(conf, cont=cont)
    if not graph or not graph.is_acyclic():
        _LOGGER.error("failed to generate dependency graph")
        return 1
    _log.section_end(_LOGGER)

    return run_graph(cont, conf, graph, startdirs)

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
    repodir = cdir / apkfoundry.MOUNTS["repodest"].lstrip("/")
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

def _cleanup(rc, cdir, delete):
    if cdir:
        if (delete == "always" or (delete == "on-success" and rc == 0)):
            _LOGGER.info("Deleting container...")
            _util.check_call(("abuild-rmtemp", cdir))

    return rc

def _ensure_dir(name):
    ok = True

    if not name.is_dir():
        name.mkdir(parents=True)
        shutil.chown(name, group="apkfoundry")
        name.chmod(0o2775)
        return ok

    if name.group() not in ("apkfoundry", "abuild"):
        ok = False
        _LOGGER.critical(
            "%s doesn't belong to group apkfoundry or abuild",
            name,
        )

    if stat.S_IMODE(name.stat().st_mode) != 0o2775:
        print(name.stat().st_mode)
        ok = False
        _LOGGER.critical(
            "%s doesn't have 2775 permissions",
            name,
        )

    return ok

def _build_list(opts):
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
        if pkgs is None:
            _LOGGER.info("No packages were changed")
        else:
            _log.msg2(_LOGGER, pkgs)
            opts.startdirs.extend(pkgs)

        _log.section_end(_LOGGER)

def _filter_list(conf, opts):
    _log.section_start(
        _LOGGER, "skip_pkgs",
        "Determining packages to skip...",
    )

    repos = conf.getmaplist("repos")
    skip = conf.getmaplist("skip")
    for i, startdir in enumerate(opts.startdirs):
        repo, _ = startdir.split("/", maxsplit=1)
        arches = repos.get(repo, None)
        if arches is None:
            _log.msg2(
                _LOGGER, "%s - repository not configured",
                startdir,
            )
            opts.startdirs[i] = None
            continue
        if opts.arch not in arches:
            _log.msg2(
                _LOGGER, "%s - repository not enabled for %s",
                startdir, opts.arch,
            )
            opts.startdirs[i] = None
            continue
        if opts.arch in skip.get(startdir, {}):
            _log.msg2(
                _LOGGER, "%s - package skipped for %s",
                startdir, opts.arch,
            )
            opts.startdirs[i] = None
            continue
    opts.startdirs = [i for i in opts.startdirs if i]

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
        help="APK architecture name (default: output of apk --print-arch)",
    )
    cont.add_argument(
        "-c", "--cache",
        help="external APK cache directory (default: none)",
    )
    cont.add_argument(
        "--directory", metavar="DIR",
        help="""Use DIR as the container root. If this does not match
        "/var/tmp/abuild.*", -D will have no effect.""",
    )
    cont.add_argument(
        "-S", "--setarch",
        help="setarch(8) architecture name (default: none)",
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
        help="project checkout directory",
    )
    checkout.add_argument(
        "-g", "--git-url",
        help="git repository URL",
    )
    checkout.add_argument(
        "--branch",
        help="""git branch for checkout (default: master). This is also
        useful when using --aportsdir in a detached HEAD state.""",
    )

    opts.add_argument(
        "-D", "--delete", choices=("always", "on-success", "never"),
        default="never",
        help="when to delete the container (default: never)",
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
        Path(opts.repodest).mkdir(parents=True, exist_ok=True)
    if opts.srcdest:
        cont_make_args += ["--srcdest", opts.srcdest]
        opts.srcdest = Path(opts.srcdest)
        if not _ensure_dir(opts.srcdest):
            return _cleanup(1, None, opts.delete)
    if opts.cache:
        cont_make_args += ["--cache", opts.cache]
        opts.cache = Path(opts.cache)
        if not _ensure_dir(opts.cache):
            return _cleanup(1, None, opts.delete)
    if opts.setarch:
        cont_make_args += ["--setarch", opts.setarch]

    cont_make_args += [
        "--arch", opts.arch,
        "--branch", opts.branch,
        "--", str(cdir), str(opts.aportsdir),
    ]
    rc, conn = apkfoundry.container.cont_make(cont_make_args)
    _log.section_end(_LOGGER)
    return rc, conn

def buildrepo(args):
    opts = _buildrepo_args(args)

    if not opts.arch:
        opts.arch = _util.get_arch()

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
        if not opts.directory.startswith("/var/tmp/abuild.") \
                and opts.delete != "never":
            _LOGGER.warning("Container DIR incompatible with abuild-rmtemp")
            _LOGGER.warning("Disabling --delete")
            opts.delete = "never"
        cdir = Path(opts.directory)
    else:
        cdir = Path(tempfile.mkdtemp(dir="/var/tmp", prefix="abuild."))
    shutil.chown(cdir, group="apkfoundry")
    cdir.chmod(0o2770)

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
        _util.check_call((
            "git", "-C", opts.aportsdir,
            "worktree", "add", ".apkfoundry", "apkfoundry",
        ))
        _log.section_end(_LOGGER)

    branchdir = _util.get_branchdir(opts.aportsdir, opts.branch)
    conf = apkfoundry.local_conf(opts.aportsdir, opts.branch)

    _build_list(opts)
    _filter_list(conf, opts)
    if not opts.startdirs:
        _LOGGER.info("No packages to build!")
        return _cleanup(0, None, opts.delete)

    rc, conn = _buildrepo_bootstrap(opts, cdir)
    if rc != 0:
        _LOGGER.error("Failed to bootstrap container")
        return _cleanup(rc, cdir, opts.delete)

    shutil.copy2(
        branchdir / "build-script",
        cdir / "af/build-script",
    )

    cont = apkfoundry.container.Container(cdir, rootd_conn=conn)
    rc = run_job(cont, conf, opts.startdirs)

    if opts.key:
        if opts.pubkey is None:
            opts.pubkey = Path(opts.key).name + ".pub"
        resignapk(cdir, opts.key, opts.pubkey)

    return _cleanup(rc, cdir, opts.delete)
