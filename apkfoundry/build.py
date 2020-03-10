# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import enum       # Enum
import logging    # getLogger
import os         # utime
import re         # compile
import shutil     # rmtree
import subprocess # call, CalledProcessError
import textwrap   # TextWrapper
from pathlib import Path

from . import EStatus, msg2, section_start, section_end
from . import container
from .digraph import generate_graph
from .socket import client_init

_LOGGER = logging.getLogger(__name__)
_REPORT_STATUSES = (
    EStatus.SUCCESS,
    EStatus.DEPFAIL,
    EStatus.FAIL,
    EStatus.ERROR,
    EStatus.CANCEL,
)
_NET_OPTION = re.compile(r"""^options=(["']?)[^"']*\bnet\b[^"']*\1""")

_wrap = textwrap.TextWrapper()

class FailureAction(enum.Enum):
    STOP = 0
    RECALCULATE = 1
    IGNORE = 2

def _stats_list(status, l):
    if not l:
        return

    _LOGGER.info("%s: %d", status.name.title(), len(l))
    msg2(_LOGGER, "\n%s\n", _wrap.fill(" ".join(l)))

def _stats_builds(done):
    _LOGGER.info("Total: %d", len(done))

    statuses = {
        status: [i for i in done if done[i] == status]
        for status in _REPORT_STATUSES
    }

    for status, startdirs in statuses.items():
        _stats_list(status, startdirs)

    for status in set(_REPORT_STATUSES) - {EStatus.SUCCESS}:
        if any(statuses[status]):
            return 1
    return 0

def run_task(cont, startdir):
    env = {}
    buildbase = Path(container.BUILDDIR) / startdir

    tmp_real = cont.cdir / str(buildbase).lstrip("/") / "tmp"
    try:
        shutil.rmtree(tmp_real.parent)
    except Exception:
        pass
    tmp_real.mkdir(parents=True, exist_ok=True)

    env["ABUILD_SRCDIR"] = str(buildbase / "src")
    env["ABUILD_PKGBASEDIR"] = str(buildbase / "pkg")
    tmp = str(buildbase / "tmp")

    env["TEMP"] = env["TMP"] = tmp
    env["TEMPDIR"] = env["TMPDIR"] = tmp
    env["HOME"] = tmp

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
        ["/af/build_script", startdir],
        repo=repo,
        env=env,
        net=net,
    )

    if rc == 0:
        try:
            shutil.rmtree(tmp_real.parent)
        except Exception:
            pass

    return rc

def run_graph(cont, graph, startdirs):
    initial = set(startdirs)
    done = {}

    # FIXME make configurable again
    on_failure = FailureAction.STOP

    while True:
        order = []
        for startdir in graph.topological_sort():
            if startdir not in initial:
                continue
            if startdir not in done:
                order.append(startdir)

        if not order:
            break

        tot = len(order)
        cur = 0

        section_start(_LOGGER, "build_order", "Build order:\n")
        for startdir in order:
            cur += 1
            msg2(_LOGGER, "(%d/%d) %s", cur, tot, startdir)
        section_end(_LOGGER)

        cur = 0
        for startdir in order:
            cur += 1
            section_start(
                _LOGGER, "build_" + startdir.replace("/", "_"),
                "(%d/%d) Start: %s", cur, tot, startdir
            )

            rc = run_task(cont, startdir)

            if rc == 0:
                section_end(_LOGGER, "(%d/%d) Success: %s", cur, tot, startdir)
                done[startdir] = EStatus.SUCCESS

            else:
                section_end(_LOGGER, "(%d/%d) Fail: %s", cur, tot, startdir)
                done[startdir] = EStatus.FAIL

                if on_failure == FailureAction.RECALCULATE:
                    section_start(_LOGGER, "recalc-order", "Recalculating build order")

                    depfails = set(graph.all_downstreams(startdir))
                    for rdep in depfails:
                        graph.delete_node(rdep)
                    graph.delete_node(startdir)

                    depfails &= initial
                    for rdep in depfails:
                        _LOGGER.error("Depfail: %s", rdep)
                        done[rdep] = EStatus.DEPFAIL

                    section_end(_LOGGER)

                elif on_failure == FailureAction.STOP:
                    _LOGGER.error("Stopping due to previous error")
                    cancels = initial - set(done.keys())
                    for rdep in cancels:
                        done[rdep] = EStatus.DEPFAIL
                    graph.reset_graph()

                elif on_failure == FailureAction.IGNORE:
                    _LOGGER.info("Ignoring error and continuing")

                break

    return _stats_builds(done)

def run_job(conn, cdir, script, startdirs):
    cont = container.Container(cdir, rootd_conn=conn)

    ignored_deps = cdir / "af/aports/.apkfoundry/ignore-deps"
    if ignored_deps.is_file():
        ignored_deps = ignored_deps.read_text().strip().splitlines()
        ignored_deps = [i.split() for i in ignored_deps]
    else:
        ignored_deps = []

    section_start(_LOGGER, "gen-build-order", "Generating build order...")
    graph = generate_graph(
        ignored_deps,
        cont=cont,
    )
    if not graph or not graph.is_acyclic():
        _LOGGER.error("failed to generate dependency graph")
        return 1
    section_end(_LOGGER)

    return run_graph(cont, graph, startdirs)
