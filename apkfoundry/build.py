# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import logging    # getLogger
import os         # utime
import re         # compile
import subprocess # PIPE
import textwrap   # TextWrapper
from pathlib import Path

from . import git_init, agent_queue, dt_timestamp
from . import container
from .digraph import Digraph
from .objects import EStatus
from .socket import client_init

_LOGGER = logging.getLogger(__name__)
_REPORT_STATUSES = (
    EStatus.IGNORE,
    EStatus.SUCCESS,
    EStatus.DEPFAIL,
    EStatus.FAIL,
    EStatus.ERROR,
    EStatus.CANCEL,
)
_NET_OPTION = re.compile(r"""^options=(["']?)[^"']*\bnet\b[^"']*\1""")

_wrap = textwrap.TextWrapper()

def _stats_list(status, l):
    if not l:
        return

    _LOGGER.info("%s: %d", status.name.title(), len(l))
    _LOGGER.info("\n%s\n", _wrap.fill(" ".join(l)))

def _stats_builds(tasks):
    _LOGGER.info("Total: %d", len(tasks))
    success = True

    statuses = {status: [] for status in _REPORT_STATUSES}
    for startdir, task in tasks.items():
        for status in statuses:
            if task.status == status:
                statuses[status].append(startdir)

    for status, tasklist in statuses.items():
        _stats_list(status, tasklist)

    rc = EStatus.SUCCESS
    for status in reversed(_REPORT_STATUSES):
        if statuses[status]:
            rc = status
            break

    return rc

def generate_graph(cont, tasks, ignored_deps):
    graph = Digraph()
    rc, proc = cont.run(
        ("/af/libexec/af-deps", *[task.startdir for task in tasks]),
        stdout=subprocess.PIPE,
        encoding="utf-8",
        skip_rootd=True,
    )
    if rc != 0:
        _LOGGER.error("af-deps failed with status %d", rc)
        return None

    origins = {}
    deps = {}
    for line in proc.stdout.split("\n"):
        line = line.strip().split(maxsplit=2)
        if not line:
            continue

        assert len(line) == 3

        if line[0] == "o":
            name = line[1]
            startdir = line[2]
            origins[name] = startdir
        elif line[0] == "d":
            startdir = line[1]
            name = line[2]
            if startdir not in deps:
                deps[startdir] = []
            deps[startdir].append(name)
        else:
            _LOGGER.error("invalid af-deps output: %r", line)
            return None

    for rdep, names in deps.items():
        graph.add_node(rdep)

        for name in names:
            if name not in origins:
                _LOGGER.warning("unknown dependency: %s", name)
                continue
            dep = origins[name]
            graph.add_node(dep)

            if dep == rdep:
                continue

            if [dep, rdep] in ignored_deps or [rdep, dep] in ignored_deps:
                continue

            graph.add_edge(dep, rdep)

    acyclic = graph.is_acyclic(exc=True)
    if acyclic is not True:
        _LOGGER.error("cycle detected: %s", " -> ".join(acyclic.cycle))
        return None

    return graph

def run_task(agent, job, cont, task, log=None):
    env = {}
    buildbase = Path(container.BUILDDIR) / task.startdir
    env["AF_TASKDIR"] = f"/af/jobs/{job.id}/{task.startdir}"
    env["AF_BRANCH"] = job.event.target
    env["ABUILD_SRCDIR"] = str(buildbase / "src")
    env["ABUILD_PKGBASEDIR"] = str(buildbase / "pkg")
    tmp = cont.cdir / str(buildbase).lstrip("/") / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    tmp = str(buildbase / "tmp")
    env["TEMP"] = env["TMP"] = tmp
    env["TEMPDIR"] = env["TMPDIR"] = tmp
    env["HOME"] = tmp

    APKBUILD = cont.cdir / f"af/info/aportsdir/{task.startdir}/APKBUILD"
    if not APKBUILD.is_file():
        raise FileNotFoundError(APKBUILD)
    net = False
    with open(APKBUILD) as f:
        for line in f:
            if _NET_OPTION.search(line) is not None:
                net = True

    timestamp = dt_timestamp(job.created)
    os.utime(APKBUILD, (timestamp, timestamp))

    if net:
        _LOGGER.info("[%s] network access enabled", task.startdir)

    if log is None:
        log = task.dir / "build.log"
        log = open(log, "w")

    try:
        rc, _ = cont.run(
            ["/af/libexec/af-worker", task.startdir],
            jobdir=job.id,
            repo=task.repo,
            stdout=log, stderr=log,
            env=env,
            net=net,
        )


    finally:
        try:
            log.close()
        except (AttributeError, TypeError):
            pass

    try:
        _LOGGER.info("[%s] pushing artifacts", job)
        agent.rsync(job.arch, "push")
    except subprocess.CalledProcessError:
        pass

    return rc

def run_graph(agent, job, graph, cont, keep_going=False, keep_files=True):
    tasks = {task.startdir: task for task in job.tasks}
    initial = {task.startdir for task in job.tasks}
    done = set()

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

        _LOGGER.info("Build order:\n")
        for startdir in order:
            cur += 1
            _LOGGER.info("\t(%d/%d) %s", cur, tot, startdir)
        _LOGGER.info("\n")

        cur = 0
        for startdir in order:
            cur += 1
            _LOGGER.info("(%d/%d) Start: %s", cur, tot, startdir)
            task = tasks[startdir]
            task.status = EStatus.START
            agent_queue.put(task)

            task.dir = job.dir / startdir
            task.dir.mkdir(parents=True, exist_ok=True)
            repo_f = cont.cdir / "af/info/repo"
            repo_f.write_text(task.repo)

            rc = run_task(agent, job, cont, task)

            if rc in (0, 10):
                _LOGGER.info("(%d/%d) Success: %s", cur, tot, startdir)
                task.status = EStatus.SUCCESS
                agent_queue.put(task)
                done.add(startdir)
                if not keep_files:
                    shutil.rmtree(cont.cdir / "build" / startdir)

            else:
                if rc == 11:
                    _LOGGER.error("(%d/%d) Fail: %s", cur, tot, startdir)
                    task.status = EStatus.FAIL
                else:
                    _LOGGER.error("(%d/%d) ERROR: %s", cur, tot, startdir)
                    task.status = EStatus.ERROR
                agent_queue.put(task)
                done.add(startdir)

                if keep_going:
                    _LOGGER.info("Recalculating build order")

                    depfails = set(graph.all_downstreams(startdir))
                    for rdep in depfails:
                        graph.delete_node(rdep)
                    graph.delete_node(startdir)

                    depfails &= initial
                    for rdep in depfails:
                        _LOGGER.error("Depfail: %s", rdep)
                        tasks[rdep].status = EStatus.DEPFAIL
                        tasks[rdep].tail = f"Depfail due to {startdir} failing"
                        agent_queue.put(tasks[rdep])
                    done.update(depfails)

                else:
                    cancels = initial - done
                    for rdep in cancels:
                        tasks[rdep].status = EStatus.CANCEL
                        tasks[rdep].tail = f"Cancelled due to {startdir} failing"
                        agent_queue.put(tasks[rdep])
                    done.update(cancels)
                    graph.reset_graph()

                break

    return _stats_builds(tasks)

def run_job(agent, job):
    job.status = EStatus.START
    agent_queue.put(job)

    topic = job.topic.split("/")
    event = job.event
    cdir = (
        agent.containers
        / f"{event.project}.{event.type}.{event.target}.{job.arch}"
    )
    job.dir = (
        agent.artdir
        / job.arch
        / f"{event.project}.{event.type}.{event.target}/jobs/{job.id}"
    )
    job.dir.mkdir(parents=True, exist_ok=True)
    (job.dir.parent.parent / "repos").mkdir(parents=True, exist_ok=True)

    if not cdir.is_dir():
        container.cont_make(
            cdir,
            branch=event.target,
            repo=job.tasks[0].repo,
            arch=job.arch,
            setarch=agent.setarch[job.arch],
            mounts={
                "jobsdir": job.dir.parent,
                "repodest": job.dir.parent.parent / "repos",
            },
        )
        bootstrap = True

    else:
        bootstrap = False

    git_init(
        cdir / "af/aports", event.clone,
        rev=event.revision,
        mrid=event.mrid, mrclone=event.mrclone, mrbranch=event.mrbranch,
    )

    rc, conn  = client_init(cdir, bootstrap=bootstrap)
    if rc != 0:
        _LOGGER.error("failed to connect to rootd")
        job.status = EStatus.ERROR
        return
    cont = container.Container(cdir, rootd_conn=conn)

    ignored_deps = cdir / "af/aports/.apkfoundry" / event.target / "ignore-deps"
    if ignored_deps.is_file():
        ignored_deps = ignored_deps.read_text().strip().splitlines()
        ignored_deps = [i.split() for i in ignored_deps]

    graph = generate_graph(cont, job.tasks, ignored_deps)
    if not graph:
        _LOGGER.error("failed to generate dependency graph")
        job.status = EStatus.ERROR
        return

    job.status = run_graph(agent, job, graph, cont)
