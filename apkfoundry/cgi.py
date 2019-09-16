# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import http   # HTTPStatus
import os     # environ, scandir
import sys    # exit
from datetime import datetime
from pathlib import Path

import jinja2 # Environment, FileSystemBytecodeCache, PackageLoader

from . import get_config, write_fifo, EStatus, EType
from .objects import Event, Job, Task, Builder, Arch

_ARTDIR = get_config("dispatch").getpath("artifacts")
_CFG = get_config("web")
BASE = _CFG["base"]
PRETTY = _CFG.getboolean("pretty")
DEBUG = _CFG.getboolean("debug")
LIMIT = _CFG.getint("limit")

if PRETTY and not BASE.endswith("/"):
    BASE += "/"

_ENV = jinja2.Environment(
    loader=jinja2.PackageLoader("apkfoundry", "templates"),
    autoescape=True,
    trim_blocks=True,
    bytecode_cache=jinja2.FileSystemBytecodeCache(),
)
_ENV.globals["event_types"] = EType
_ENV.globals["statuses"] = EStatus
_ENV.globals["base"] = BASE
_ENV.globals["css"] = _CFG["css"]
_ENV.globals["pretty"] = PRETTY

_RESPONSE_HEADER = """HTTP/1.1 {status} {statusphrase}
Content-type: {content_type}; charset=utf-8
"""

def setenv(key, value):
    _ENV.globals[key] = value

def getnow():
    return datetime.utcnow().replace(microsecond=0)

def timeelement(dt, now):
    delta = (now - dt)
    days = delta.days
    delta = delta.seconds
    hours, i = divmod(delta, 3600)
    minutes = i // 60

    if days:
        fmt = "{days}d{hours:02d}h{minutes:02d}m"
    elif hours:
        fmt = "{hours}h{minutes:02d}m"
    else:
        fmt = "{minutes}m"

    delta = fmt.format(days=days, hours=hours, minutes=minutes)
    return (dt, delta)

def response(status, content_type):
    status = http.HTTPStatus(status)
    statusphrase = status.phrase
    status = status.value

    print(_RESPONSE_HEADER.format(
        status=status,
        statusphrase=statusphrase,
        content_type=content_type,
    ))

def error(status, message):
    response(status, "text/html")

    tmpl = _ENV.get_template("error.tmpl")
    print(tmpl.render(
        title=message,
    ))

    sys.exit(1)

def html_ok():
    response(200, "text/html")

def home_page(db):
    html_ok()
    projects = db.execute("SELECT DISTINCT project FROM events").fetchall()
    projects = [project[0] for project in projects]

    tmpl = _ENV.get_template("home.tmpl")
    print(tmpl.render(
        projects=projects,
    ))

def events_page(db, query, project_page=False):
    events = Event.db_search(db, **query).fetchall()
    project = jinja2.Undefined(name="project")

    if project_page:
        if not events:
            error(404, "Project not found")

        project = query["project"]

    html_ok()
    now = getnow()

    for i, event in enumerate(events):
        event.created = timeelement(event.created, now)
        event.updated = timeelement(event.updated, now)

        jobs = db.execute(
            "SELECT COUNT(*) FROM jobs WHERE eventid = ?;", (event.id,),
        )
        (jobs,) = jobs.fetchone()

        tasks = db.execute(
            "SELECT COUNT(*) FROM tasks_full WHERE eventid = ?;", (event.id,),
        )
        (tasks,) = tasks.fetchone()

        events[i] = (event, jobs, tasks)

    tmpl = _ENV.get_template("events.tmpl")
    print(tmpl.render(
        events=events,
        project_page=project_page,
        project=project,
    ))

def jobs_page(db, query, event_page=False):
    event = jinja2.Undefined(name="event")
    now = getnow()

    if event_page:
        event = Event.db_search(db, eventid=query["eventid"]).fetchone()

        if event is None:
            error(404, "Unknown event")

        event.created = timeelement(event.created, now)
        event.updated = timeelement(event.updated, now)

    html_ok()
    jobs = Job.db_search(db, **query).fetchall()

    for job in jobs:
        job.created = timeelement(job.created, now)
        job.updated = timeelement(job.updated, now)

        job.tasks = db.execute(
            "SELECT COUNT(*) FROM tasks WHERE jobid = ?;", (job.id,),
        )
        (job.tasks,) = job.tasks.fetchone()

    tmpl = _ENV.get_template("jobs.tmpl")
    print(tmpl.render(
        event=event,
        event_page=event_page,
        jobs=jobs,
    ))

def tasks_page(db, query, job_page=False):
    job = jinja2.Undefined(name="job")
    now = getnow()

    if job_page:
        job = Job.db_search(db, jobid=query["jobid"]).fetchone()

        if job is None:
            error(404, "Unknown job")

        job.created = timeelement(job.created, now)
        job.updated = timeelement(job.updated, now)

    html_ok()
    tasks = Task.db_search(db, **query).fetchall()

    for i, task in enumerate(tasks):
        if task.maintainer is None:
            task.maintainer = "None"

        task.created = timeelement(task.created, now)
        task.updated = timeelement(task.updated, now)

    tmpl = _ENV.get_template("tasks.tmpl")
    print(tmpl.render(
        job=job,
        job_page=job_page,
        tasks=tasks,
    ))

def artifacts_page(db, query):
    now = getnow()

    task = Task.db_search(db, taskid=query["taskid"]).fetchone()
    if task is None:
        error(404, "Unknown task")

    task.created = timeelement(task.created, now)
    task.updated = timeelement(task.updated, now)
    if task.maintainer is None:
        task.maintainer = "None"

    job = Job.db_search(db, jobid=task.job).fetchone()
    event = Event.db_search(db, eventid=job.event).fetchone()

    task.dir = (
        _ARTDIR
        / job.arch
        / f"{event.project}.{event.type}.{event.target}/jobs/{job.id}"
        / task.startdir
    )

    html_ok()

    if task.dir.exists():
        dir_exists = True
        art_uri = _CFG.getpath("artifacts")
        artifacts = [
            (i, art_uri / Path(i).relative_to(_ARTDIR)) \
            for i in os.scandir(task.dir)
        ]
    else:
        artifacts = jinja2.Undefined(name="artifacts")
        dir_exists = False

    tmpl = _ENV.get_template("artifacts.tmpl")
    print(tmpl.render(
        task=task,
        dir_exists=dir_exists,
        artifacts=artifacts,
    ))

def status_page(db, query):
    builders = Builder.db_search(db)
    title = "System status"
    html_ok()
    now = getnow()

    arches = []
    for builder in builders:
        arches.extend(builder.arches.keys())

    builders.append(
        Builder(
            name=None,
            arches={name: Arch() for name in arches},
        )
    )

    for builder in builders:
        if builder.name:
            builder.updated = timeelement(builder.updated, now)

        for name, arch in builder.arches.items():
            if builder.name is None:
                # Oldest job
                arch.curr_jobs = Job.db_search(
                    db,
                    builder="None",
                    status=EStatus.NEW,
                    arch=name,
                    asc=True,
                ).fetchall() or []

            for job in arch.curr_jobs:
                job.updated = timeelement(job.updated, now)

            if arch.prev_job:
                arch.prev_job.updated = timeelement(arch.prev_job.updated, now)

    for i, name in enumerate(arches):
        new = db.execute(
            "SELECT COUNT(*) FROM jobs WHERE arch GLOB ? AND status = ?;",
            (name, EStatus.NEW),
        ).fetchone()[0]
        started = db.execute(
            "SELECT COUNT(*) FROM jobs WHERE arch GLOB ? AND status = ?;",
            (name, EStatus.START),
        ).fetchone()[0]

        arches[i] = (name, new, started)

    tmpl = _ENV.get_template("status.tmpl")
    print(tmpl.render(
        title=title,
        arches=arches,
        builders=builders,
        dispatch_online=write_fifo("2"),
    ))
