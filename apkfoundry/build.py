# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import logging    # getLogger
import subprocess # PIPE
import textwrap   # TextWrapper
from pathlib import Path

from . import git_init, agent_queue
from . import container
from .digraph import Digraph
from .objects import EStatus
from .socket import client_init

_LOGGER = logging.getLogger(__name__)
_REPORT_STATUSES = (
    EStatus.SUCCESS,
    EStatus.IGNORE,
    EStatus.CANCEL,
    EStatus.DEPFAIL,
    EStatus.FAIL,
    EStatus.ERROR,
)

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

        if statuses[status] and status & EStatus.ERROR:
            success = False

    return success

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

def run_task(job, cont, task, log=None):
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

    if log is None:
        log = task.dir / "log"
        log = open(log, "w")

    try:
        rc, _ = cont.run(
            ["/af/libexec/af-worker", task.startdir],
            jobid=job.id,
            repo=task.repo,
            stdout=log, stderr=log,
            env=env,
        )

    finally:
        try:
            log.close()
        except (AttributeError, TypeError):
            pass

    return rc == 0

def run_graph(job, graph, cont, keep_going=False, keep_files=True):
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

            if not run_task(job, cont, task):
                _LOGGER.error("(%d/%d) Fail: %s", cur, tot, startdir)
                task.status = EStatus.FAIL
                agent_queue.put(task)
                done.add(startdir)

                if keep_going:
                    _LOGGER.info("Recalculating build order")

                    depfails = graph.all_downstreams(startdir)
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

            else:
                _LOGGER.info("(%d/%d) Success: %s", cur, tot, startdir)
                task.status = EStatus.SUCCESS
                agent_queue.put(task)
                done.add(startdir)
                if not keep_files:
                    shutil.rmtree(cont.cdir / "build" / startdir)

    return _stats_builds(tasks)

def run_job(agent, job):
    topic = job.topic.split("/")
    event = job.event
    cdir = f"{event.project}.{event.type}.{event.target}.{job.arch}"
    cdir = agent.containers / cdir
    job.dir = agent.jobsdir / str(job.id)

    if not cdir.is_dir():
        container.cont_make(
            cdir,
            branch=event.target,
            repo=job.tasks[0].repo,
            arch=job.arch,
            setarch=agent.setarch[job.arch],
            mounts={
                "jobsdir": agent.jobsdir,
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
        agent_queue.put(job)
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
        agent_queue.put(job)
        return

    try:
        run_graph(job, graph, cont)
    except Exception as e:
        _LOGGER.exception("unhandled exception", exc_info=e)
        job.status = EStatus.ERROR
        agent_queue.put(job)
