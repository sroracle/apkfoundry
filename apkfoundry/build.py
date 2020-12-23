# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019-2020 Max Rees
# See LICENSE for more information.
import argparse   # ArgumentParser, SUPPRESS
import enum       # Enum, IntFlag, unique
import functools  # partial
import logging    # getLogger
import os         # access, *_OK, walk
import re         # compile
import shutil     # chown, copy2, rmtree
import subprocess # check_output
import tempfile   # mkdtemp
import textwrap   # TextWrapper
import time       # time
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

def _run_env(cont, startdir):
    buildbase = Path(apkfoundry.MOUNTS["builddir"]) / startdir

    tmp_real = cont.cdir / "af/config/builddir" / startdir / "tmp"
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

    return env, tmp_real

def run_task(cont, conf, startdir, script):
    env, tmp = _run_env(cont, startdir)
    repo = startdir.split("/")[0]

    APKBUILD = cont.cdir / f"af/config/aportsdir/{startdir}/APKBUILD"
    net = conf.getboolean("build.networking")
    if not net:
        with open(APKBUILD) as f:
            for line in f:
                if _NET_OPTION.search(line) is not None:
                    net = True
                    break
    if net:
        _LOGGER.warning("%s: network access enabled", startdir)

    rc, _ = cont.run(
        [script, startdir],
        repo=repo,
        env=env,
        net=net,
        chdir=Path(apkfoundry.MOUNTS["aportsdir"]) / startdir,
    )

    if rc == 0:
        try:
            # Only remove TEMP files, not src/pkg
            _LOGGER.info("Removing package tmpfiles")
            shutil.rmtree(tmp)
        except (FileNotFoundError, PermissionError):
            pass

    return rc

def _interrupt(cont, startdir):
    prompt = """Interactive mode options:

* s - Shell
* n - Networked shell
* S - Superuser shell (with RW rootfs and networking access)
* i - Ignore and continue
* r - Recalculate and continue
* ^D - exit

> """

    try:
        response = input(prompt).strip()
    except EOFError:
        return FailureAction.STOP
    if response not in ("s", "n", "S", "i", "r"):
        return None

    if response == "i":
        return FailureAction.IGNORE
    if response == "r":
        return FailureAction.RECALCULATE

    if response in ("s", "n"):
        env, _ = _run_env(cont, startdir)
    else:
        env = {}

    net = response in ("n", "S")
    su = response == "S"
    ro_root = response != "S"
    skip_sudo = response == "S"

    cont.run(
        ["sh", "-"],
        env=env,
        su=su,
        ro_root=ro_root,
        skip_refresh=True,
        skip_sudo=skip_sudo,
        net=net,
        setsid=False,
        chdir=Path(apkfoundry.MOUNTS["aportsdir"]) / startdir,
    )

    return None

def run_graph(cont, conf, graph, opts):
    initial = set(opts.startdirs)
    done = {}

    try:
        on_failure = FailureAction[conf["build.on-failure"].upper()]
    except KeyError:
        _LOGGER.error(
            "build.on-failure = %s is invalid; defaulting to STOP",
            conf["build.on-failure"].upper(),
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

            rc = run_task(cont, conf, startdir, opts.build_script)

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

                if opts.interactive:
                    action = _interrupt(cont, startdir)
                    while action is None:
                        action = _interrupt(cont, startdir)
                else:
                    action = on_failure

                if action == FailureAction.RECALCULATE:
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

                elif action == FailureAction.STOP:
                    _LOGGER.error("Stopping due to previous error")
                    cancels = initial - set(done.keys())
                    for rdep in cancels:
                        done[rdep] = Status.DEPFAIL
                    graph.reset_graph()

                elif action == FailureAction.IGNORE:
                    _LOGGER.info("Ignoring error and continuing")

                break

    return _stats_builds(done)

def run_job(cont, conf, opts):
    _log.section_start(
        _LOGGER, "gen-build-order", "Generating build order...",
    )
    graph = apkfoundry.digraph.generate_graph(conf, cont=cont)
    if not graph or not graph.is_acyclic():
        _LOGGER.error("failed to generate dependency graph")
        return 1
    _log.section_end(_LOGGER)

    return run_graph(cont, conf, graph, opts)

def run_after(rc, cont, conf, afterdir, script):
    _log.section_start(
        _LOGGER, "run-after-script", "Running 'after' script...",
    )
    rc, _ = cont.run(
        [script],
        repo=conf.get("after.repo", conf["repo.default"]),
        net=conf.getboolean("after.networking"),
        env={
            "AF_RC": str(rc),
            "AF_AFTERDIR": "/af/config/afterdir",
            "AF_FILELIST": "/af/config/filelist",
        },
    )
    _log.section_end(_LOGGER)
    return rc

def changed_pkgs(conf, opts):
    gitdir = ["-C", str(opts.aportsdir)] \
        if opts.aportsdir else []
    pickaxe = ["-G", "^pkg(ver|rel)="] \
        if conf.getboolean("build.only-changed-versions") else []

    pkgs = subprocess.check_output(
        ("git", *gitdir, "diff-tree",
         "-r", "--name-only", "--diff-filter", "dxu", *pickaxe,
         *opts.rev_range.split(), "--", "*/*/APKBUILD"),
        encoding="utf-8"
    ).splitlines()
    return [i.replace("/APKBUILD", "") for i in pkgs]

def _save_filelist(cont, start):
    files = []
    repodest = cont.cdir / "af/config/repodest"
    for dpath, _, fnames in os.walk(repodest):
        dpath = Path(dpath)
        for fname in fnames:
            fname = dpath / fname
            if fname.stat().st_mtime > start:
                files.append(str(fname.relative_to(repodest)))

    files = "\n".join(sorted(files)) + "\n"
    filelist = cont.cdir / "af/config/filelist"
    filelist.write_text(files)

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
        pkgs = changed_pkgs(conf, opts)
        _log.msg2(_LOGGER, pkgs)
        _log.section_end(_LOGGER)
        opts.startdirs.extend(_filter_list(conf, opts, pkgs))

def _filter_list(conf, opts, startdirs):
    _log.section_start(
        _LOGGER, "skip_pkgs",
        "Determining packages to skip...",
    )

    repos = conf.getmaplist("repo.arch")
    skip = conf.getmaplist("build.skip")
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
        "--arch",
        help=f"""APK architecture name (default:
        {apkfoundry.DEFAULT_ARCH})""",
    )
    cont.add_argument("-A", help=argparse.SUPPRESS)
    cont.add_argument(
        "--cache-apk",
        help="external APK cache directory (default: none)",
    )
    cont.add_argument("-c", "--cache", help=argparse.SUPPRESS)
    cont.add_argument(
        "--cache-src",
        help="external source file cache directory (default: none)",
    )
    cont.add_argument("-s", "--srcdest", help=argparse.SUPPRESS)
    cont.add_argument(
        "--directory", metavar="CDIR",
        help=f"""use CDIR as the container root (default: temporary
        directory in {apkfoundry.LOCALSTATEDIR})""",
    )
    cont.add_argument(
        "--setarch",
        help="""setarch(8) architecture name (default: look in site
        configuration, otherwise none)""",
    )
    cont.add_argument("-S", help=argparse.SUPPRESS)

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
        "-o", "--config-option", action="append",
        metavar="KEY=VALUE",
        help="""override project configuration settings (can be
        specified multiple times)""",
    )
    opts.add_argument(
        "--afterdir", metavar="DIR",
        help="""mount DIR to $AF_AFTERDIR to supplement
        --after-script""",
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
        "-i", "--interactive", action="store_true",
        help="interactively stop when a package fails to build",
    )
    opts.add_argument(
        "-r", "--rev-range",
        help="git revision range for changed APKBUILDs",
    )
    opts.add_argument(
        "--build-script",
        help="""Alternative build script to use instead of
        $AF_BRANCHDIR/build. Must be an absolute path underneath the
        container root.""",
    )
    opts.add_argument("--script", help=argparse.SUPPRESS)
    opts.add_argument(
        "--after-script",
        help="""Alternative after script to use instead of
        $AF_BRANCHDIR/after. Must be an absolute path underneath the
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
    opts = opts.parse_args(args)
    if opts.A:
        _LOGGER.warning("-A is deprecated. Use --arch.")
        opts.arch = opts.A
    if opts.cache:
        _LOGGER.warning("-c/--cache is deprecated. Use --cache-apk.")
        opts.cache_apk = opts.cache
    if opts.srcdest:
        _LOGGER.warning("-s/--srcdest is deprecated. Use --cache-src.")
        opts.cache_src = opts.srcdest
    if opts.S:
        _LOGGER.warning("-S is deprecated. Use --setarch.")
        opts.setarch = opts.S
    if opts.script:
        _LOGGER.warning("--script is deprecated. Use --build-script.")
        opts.build_script = opts.script

    return opts

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
    if opts.cache_src:
        cont_make_args += ["--cache-src", opts.cache_src]
        opts.cache_src = Path(opts.cache_src)
        if not _ensure_dir(opts.cache_src):
            return None
    if opts.cache_apk:
        cont_make_args += ["--cache-apk", opts.cache_apk]
        opts.cache_apk = Path(opts.cache_apk)
        if not _ensure_dir(opts.cache_apk):
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

    if opts.dry_run:
        opts.delete = "always"

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
    if opts.config_option:
        conf = dict(map(lambda i: i.split("=", maxsplit=1), opts.config_option))
    else:
        conf = None
    conf = apkfoundry.proj_conf(opts.aportsdir, opts.branch, conf)

    if not opts.build_script:
        opts.build_script = Path(apkfoundry.MOUNTS["aportsdir"]) \
            / ".apkfoundry" / branchdir.name / "build"
    if not opts.after_script:
        opts.after_script = Path(apkfoundry.MOUNTS["aportsdir"]) \
            / ".apkfoundry" / branchdir.name / "after"

    _build_list(conf, opts)
    if not opts.startdirs:
        _LOGGER.info("No packages to build!")
        return _cleanup(0, cdir, opts.delete)

    if opts.dry_run:
        return _cleanup(0, cdir, opts.delete)

    cont = _buildrepo_bootstrap(opts, cdir)
    if not cont:
        _LOGGER.error("Failed to bootstrap container")
        return _cleanup(1, cont, opts.delete)

    start = time.time()
    rc = run_job(cont, conf, opts)
    _save_filelist(cont, start)
    rc = run_after(rc, cont, conf, opts.afterdir, opts.after_script) or rc

    return _cleanup(rc, cont, opts.delete)
