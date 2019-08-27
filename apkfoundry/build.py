# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import logging    # getLogger
import subprocess # PIPE
import os         # environ
from pathlib import Path

from . import git_init, agent_queue
from . import container
from .digraph import Digraph
from .objects import AFStatus, Task, AFEventType
from .root import client_init

_LOGGER = logging.getLogger(__name__)
_REPORT_STATUSES = (
    AFStatus.SUCCESS,
    AFStatus.IGNORE,
    AFStatus.CANCEL,
    AFStatus.DEPFAIL,
    AFStatus.FAIL,
    AFStatus.ERROR,
)

def _stats_list(status, l):
    if not l:
        return

    _LOGGER.info("%s: %d", status.name.title(), len(l))
    _LOGGER.info("\n%s\n", _wrap.fill(" ".join(l)))

def _stats_builds(tasks):
    _LOGGER.info("Total: %d", len(tasks))
    success = True

    statuses = {status: [] for status in _REPORT_STATUSES}
    for startdir, task in tasks:
        for status in statuses:
            if task.status == status:
                groups[status].append(startdir)

    for status in statuses:
        _stats_list(status, statuses[status])

        if statuses[status] and status & AFStatus.ERROR:
            success = False

    return success

def generate_graph(cont, tasks):
    graph = Digraph()
    rc, proc = cont.run(
        ("/af/libexec/af-deps", *[task.startdir for task in tasks]),
        stdout=subprocess.PIPE,
        encoding="utf-8",
    )
    if rc:
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

    errors = False
    for rdep, names in deps.items():
        graph.add_node_if_not_exists(rdep)

        for name in names:
            if name not in origins:
                _LOGGER.error("unknown dependency: %s", name)
                errors = True
                continue
            dep = origins[name]
            graph.add_node_if_not_exists(dep)

            if dep == rdep:
                continue

            try:
                graph.add_edge(dep, rdep)
            except DAGValidationError:
                _LOGGER.error("cycle detected: %s depends on %s", dep, rdep)
                errors = True

    if errors:
        return None

    return graph

def run_startdir(cont, branch, taskdir, startdir, log=None):
    env = os.environ.copy()

    buildbase = Path(container.BUILDDIR) / startdir
    env["AF_TASKDIR"] = "/" + str(taskdir.relative_to(cont.cdir))
    env["AF_BRANCH"] = branch
    env["ABUILD_SRCDIR"] = str(buildbase / "src")
    env["ABUILD_PKGBASEDIR"] = str(buildbase / "pkg")
    tmp = cont.cdir / "af/build" / startdir / "tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    tmp = str(buildbase / "tmp")
    env["TEMP"] = env["TMP"] = tmp
    env["TEMPDIR"] = env["TMPDIR"] = tmp
    env["HOME"] = tmp

    if log is None:
        log = taskdir / "log"
        log = open(log, "w")

    try:
        _, proc = cont.run(
            ["/af/libexec/af-worker", startdir],
            stdout=log, stderr=log,
            env=env,
            check=True,
        )

    except subprocess.CalledProcessError:
        raise

    finally:
        try:
            log.close()
        except (AttributeError, TypeError):
            pass

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
            task.status = AFStatus.START
            agent_queue.put(task)

            try:
                taskdir = jobdir / startdir
                taskdir.mkdir(parents=True, exist_ok=True)
                repo_f = cont.cdir / "af/info/repo"
                repo_f.write_text(repo)
                run_startdir(cont, job.target, taskdir, startdir)

            except subprocess.CalledProcessError as e:
                _LOGGER.error("(%d/%d) Fail: %s (%d)", cur, tot, startdir, e.returncode)
                task.status = AFStatus.FAIL
                agent_queue.put(task)
                done.add(startdir)

                if keep_going:
                    _LOGGER.info("Recalculating build order")

                    depfails = graph.all_downstreams(startdir)
                    for rdep in depfails:
                        graph.delete_node_if_exists(rdep)
                    graph.delete_node_if_exists(startdir)

                    depfails &= initial
                    for rdep in depfails:
                        _LOGGER.error("Depfail: %s", rdep)
                        tasks[rdep].status = AFStatus.DEPFAIL
                        tasks[rdep].tail = f"Depfail due to {startdir} failing"
                        agent_queue.put(tasks[rdep])
                    done.update(depfails)

                else:
                    cancels = initial - done
                    cancels.remove(startdir)
                    for rdep in cancels:
                        tasks[rdep].status = AFStatus.CANCEL
                        tasks[rdep].tail = f"Cancelled due to {startdir} failing"
                        agent_queue.put(tasks[rdep])
                    done.update(cancels)
                    graph.reset_graph()

                break

            else:
                _LOGGER.info("(%d/%d) Success: %s", cur, tot, startdir)
                task.status = AFStatus.SUCCESS
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
    jobdir = agent.jobsdir / str(job.id)

    if not cdir.is_dir():
        container.cont_make(
            cdir,
            branch=event.target,
            repo=job.tasks[0].repo,
            arch=job.arch,
            setarch=agent.arches[job.arch],
        )
        bootstrap = True

    else:
        bootstrap = False

    kwargs = {
        "rev": event.revision,
        "hard": True,
    }
    if event.type == AFEventType.MR:
        kwargs["mrid"] = event.mrid
        kwargs["mrclone"] = event.mrclone
        kwargs["mrbranch"] = event.mrbranch
    git_init(cdir / "af/aports", event.clone, **kwargs)

    sock = client_init(cdir, bootstrap=bootstrap)
    cont = container.Container(cdir, root_fd=sock.fileno())

    graph = generate_graph(cont, job.tasks)
    if not graph:
        _LOGGER.error("failed to generate dependency graph")
        job.status = AFStatus.ERROR
        agent_queue.put(job)
        return

    try:
        run_graph(agent, job, graph, cont)
    except Exception as e:
        _LOGGER.exception("unhandled exception", exc_info=e)
        job.status = AFStatus.ERROR
        agent_queue.put(job)
