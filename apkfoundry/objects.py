# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import enum
import functools
import json
import logging
import sqlite3
import subprocess
from datetime import datetime
from typing import List

import attr

from . import dispatch_queue, get_output, get_config, git_init

@enum.unique
class AFEventType(enum.IntEnum):
    PUSH = 1
    MR = 2
    MANUAL = 4

    def __str__(self):
        return self.name

@enum.unique
class AFStatus(enum.IntFlag):
    NEW = 1
    REJECT = 2
    START = 4
    DONE = 8
    ERROR = DONE | 16      # 24
    CANCEL = ERROR | 32    # 56
    SUCCESS = DONE | 64    # 72
    FAIL = ERROR | 128     # 152
    DEPFAIL = CANCEL | 256 # 312
    IGNORE = DONE | 512    # 520

    def __str__(self):
        return self.name

_LOGGER = logging.getLogger(__name__)

_PROJECTS_HOME = get_config("dispatch").getpath("projects")

def _validate_schema(schema, dct):
    for (key, value) in schema.items():
        if key.startswith("_"):
            continue

        assert key in dct, f"Missing required key {key}"

        if value is None:
            continue

        if type(value) == type:
            need_type = value
            descend = False
        else:
            need_type = type(value)
            descend = True

        assert type(dct[key]) == need_type, \
            f"{key} must be {need_type.__name__}"

        if descend and type(dct[key]) == list:
            for i in dct[key]:
                _validate_schema(value[0], i)

        elif descend and type(dct[key]) == dict:
            _validate_schema(value, dct[key])

        elif descend:
            assert dct[key] == value, f"{key} must equal {value}"

class JSONSchema:
    __slots__ = ("full_schema",)

    def __init__(self, **kwargs):
        self.full_schema = {}

        for cls in self.__class__.__mro__:
            if cls.__name__ in ("object", "JSONSchema"):
                continue

            if hasattr(cls, "schema"):
                self.full_schema.update(cls.schema)

        _validate_schema(self.full_schema, kwargs)

        for key in self.full_schema:
            setattr(self, key, kwargs[key])

    def __getitem__(self, key):
        return getattr(self, key)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def __delitem__(self, key):
        self.__delattr__(key)

    def __iter__(self):
        yield from self.__slots__

    def __contains__(self, key):
        return hasattr(self, key)

    def to_dict(self):
        return {key: self[key] for key in self.full_schema}

def _db_search(classes, db, where=None, **query):
    if where is None:
        where = []

    full = False
    tables = classes[0]._tables

    for field, value in query.items():
        if not value or field.startswith("_"):
            continue

        for cls in classes:
            if field == cls.__name__.lower() + "id":
                where.append(f"{field} = :{field}")
                continue

            fields = attr.fields_dict(cls)
            if field in fields:
                if fields[field].type is str:
                    where.append(f"IFNULL({field}, 'None') GLOB :{field}")
                else:
                    where.append(f"{field} = :{field}")

                break

        else:
            cls = classes[0]

        if cls != classes[0]:
            full = True

    table = tables[-1] if full else tables[0]
    sql = f"SELECT * FROM {table}"
    if where:
        sql += " WHERE " + " AND ".join(where)

    if query.get("limit", None):
        sql += " LIMIT :limit"
    if query.get("offset", None):
        sql += " OFFSET :offset"
    sql += ";"

    old_factory = db.row_factory
    db.row_factory = cls.from_db_row
    rows = db.execute(sql, query)
    db.row_factory = old_factory
    return rows

@attr.s(kw_only=True, slots=True)
class Task:
    id: int = attr.ib(default=None)
    job = attr.ib() # Job or int
    repo: str = attr.ib()
    pkg: str = attr.ib()
    maintainer: str = attr.ib(default=None)
    tail: str = attr.ib(default=None)
    artifacts = attr.ib(default=None)

    created: datetime = attr.ib(default=None)
    updated: datetime = attr.ib(default=None)

    _tables = ("tasks", "tasks_full")

    _status = attr.ib(
        default=AFStatus.NEW, validator=attr.validators.in_(AFStatus)
    )
    _topic = attr.ib(default=None)

    def __str__(self):
        return self.topic

    @property
    def topic(self, inner=False):
        if self._topic is not None:
            return self._topic

        if isinstance(self.job, int):
            job_topic = f"@/@/@/@/@/@/{self.job}"
        else:
            job_topic = self.job.topic(inner=True)

        if inner:
            prefix = ()
        else:
            prefix = ("tasks", str(self.status))

        return "/".join((
            *prefix,
            job_topic,
            self.repo,
            self.pkg,
            str(self.id) if self.id else "@",
        ))

    @topic.setter
    def topic(self, value):
        self._topic = value

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value
        self._topic = None

    @property
    def startdir(self):
        return f"{self.repo}/{self.pkg}"

    def to_mqtt(self):
        payload = attr.asdict(self, recurse=True)
        payload = json.dumps(payload)
        return payload.encode("utf-8")

    @classmethod
    def from_mqtt(cls, topic, payload):
        assert topic.startswith("tasks/")
        payload = payload.decode("utf-8")
        payload = json.loads(payload)

        return cls(
            **payload,
            topic=topic,
        )

    def db_process(self, db):
        db.execute(
            """UPDATE tasks SET status = ?, tail = ?
            WHERE jobid = ? AND repo = ? AND pkg = ?;""",
            (self.status, self.tail, self.job, self.repo, self.pkg),
        )
        db.commit()

    @classmethod
    def from_db_row(cls, cursor_, row):
        return cls(
            id=row[0],
            job=row[1],
            repo=row[2],
            pkg=row[3],
	    maintainer=row[4],
            status=AFStatus(row[5]),
            tail="" if row[6] is None else row[6],
            created=row[7],
            updated=row[8],
        )

    @classmethod
    def db_search(cls, db, where=None, **query):
        return _db_search((cls, Job, Event), db, where, **query)

@attr.s(kw_only=True, slots=True)
class Job:
    id: int = attr.ib(default=None)
    event = attr.ib() # Event or int
    builder: str = attr.ib(default=None)
    arch: str = attr.ib()

    created: datetime = attr.ib(default=None)
    updated: datetime = attr.ib(default=None)

    tasks = attr.ib(default=None)
    payload = attr.ib(default=None)
    dir = attr.ib(default=None)

    _tables = ("jobs", "jobs_full")

    _status = attr.ib(
        default=AFStatus.NEW, validator=attr.validators.in_(AFStatus)
    )
    _topic = attr.ib(default=None)

    def __str__(self):
        return self.topic

    @property
    def topic(self, inner=False):
        if self._topic is not None:
            return self._topic

        if isinstance(self.event, int):
            event_topic = f"@/@/@/{self.event}"
        else:
            event_topic = self.event.topic(inner=True)

        if inner:
            prefix = ()
        else:
            prefix = ("jobs", str(self.status))

        self._topic = "/".join((
            *prefix,
            event_topic,
            self.builder or "@",
            self.arch,
            str(self.id) if self.id else "@",
        ))

        return self._topic

    @topic.setter
    def topic(self, value):
        self._topic = value

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value
        self._topic = None

    def to_mqtt(self):
        payload = attr.asdict(self, recurse=True)
        payload = json.dumps(payload)
        return payload.encode("utf-8")

    @classmethod
    def from_mqtt(cls, topic, payload):
        assert topic.startswith("jobs/")
        payload = payload.decode("utf-8")
        payload = json.loads(payload)

        return cls(
            **payload,
            topic=topic,
        )

    @classmethod
    def from_db_row(cls, cursor_, row):
        return cls(
            id=row[0],
            event=row[1],
            builder=row[2],
            arch=row[3],
            status=AFStatus(row[4]),
            created=row[5],
            updated=row[6],
        )

    def db_process(self, db):
        pass
        # XXX hmm
#        db.execute(
#            "UPDATE jobs SET builder = ?, status = ? WHERE job = ?;",
#            (self.builder, self.status, self.job),
#        )
#
#        if self.status & (AFStatus.START | AFStatus.DONE):
#            db.execute(
#                "UPDATE tasks SET status = ? WHERE job = ? AND status = 'new';",
#                (self.status, self.job),
#            )
#
#        db.commit()

    @classmethod
    def db_search(cls, db, where=None, **query):
        return _db_search((cls, Event), db, where, **query)

@attr.s(kw_only=True, slots=True)
class Event:
    id: int = attr.ib(default=None)
    project: str = attr.ib()
    type: int = attr.ib(
        default=AFEventType.PUSH, validator=attr.validators.in_(AFEventType)
    )
    clone: str = attr.ib()
    target: str = attr.ib()
    revision: str = attr.ib()
    user: str = attr.ib()
    reason: str = attr.ib()

    created: datetime = attr.ib(default=None)
    updated: datetime = attr.ib(default=None)

    mrid: int = attr.ib(default=None)
    mrclone: str = attr.ib(default=None)
    mrbranch: str = attr.ib(default=None)

    _tables = ("events",)

    _dir = attr.ib(default=None)
    _status = attr.ib(
        default=AFStatus.NEW, validator=attr.validators.in_(AFStatus)
    )
    _topic = attr.ib(default=None)

    def __attrs_post_init__(self):
        self._dir = _PROJECTS_HOME / self.project

    def __str__(self):
        return self.topic

    @property
    def topic(self, inner=False):
        if self._topic is not None:
            return self._topic

        if inner:
            prefix = ()
        else:
            prefix = ("events", str(self.status))

        self._topic = "/".join((
            *prefix,
            self.project,
            str(self.type),
            self.target,
            str(self.id) if self.id else "@",
        ))
        return self._topic

    @topic.setter
    def topic(self, value):
        self._topic = value

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, value):
        self._status = value
        self._topic = None

    @classmethod
    def from_db_row(cls, cursor_, row):
        return cls(
            id=row[0],
            project=row[1],
            type=AFEventType(row[2]),
            clone=row[3],
            target=row[4],
            revision=row[5],
            user=row[6],
            reason=row[7],
            status=AFStatus(row[8]),
            created=row[9],
            updated=row[10],

            mrid=row[11],
            mrclone=row[12],
            mrbranch=row[13],
        )

    @classmethod
    def db_search(cls, db, where=None, **query):
        return _db_search((cls,), db, where, **query)

    def _db_add(self, db):
        assert self.id is None, "_db_add after Event.id"
        _LOGGER.info("[%s] Adding event to database", str(self))

        cursor = db.execute("""
            INSERT INTO events (
                project,
                type,
                clone,
                target,
                mrid,
                mrclone,
                mrbranch,
                revision,
                user,
                reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
            (
                self.project,
                self.type,
                self.clone,
                self.target,
                self.mrid,
                self.mrclone,
                self.mrbranch,
                self.revision,
                self.user,
                self.reason,
            ),
        )

        self.id = cursor.lastrowid
        db.commit()

    def _debug_dump(self):
        _LOGGER.debug("[%s] Clone: %s", str(self), self.clone)
        _LOGGER.debug("[%s] Revision: %s", str(self), self.revision)
        _LOGGER.debug("[%s] User: %s", str(self), self.user)
        _LOGGER.debug("[%s] Reason: %s", str(self), self.reason)

    def _calc_startdirs(self):
        raise NotImplementedError

    def _calc_maintainers(self, startdirs):
        _LOGGER.info("[%s] Retrieving maintainers", str(self))
        maintainers = get_output(
            "af-maintainer", *startdirs, cwd=self._dir,
        )
        maintainers = maintainers.strip().splitlines()
        maintainers = [line.strip().split(maxsplit=1) for line in maintainers]
        maintainers = {line[0]: line[1] for line in maintainers if line}

        return maintainers

    def _calc_arches(self, startdirs):
        _LOGGER.info("[%s] Generating architecture list", str(self))
        lines = get_output(
            "af-arch", "-b", self.target,
            *startdirs, cwd=self._dir,
        ).strip().splitlines()

        arches = {}
        for line in lines:
            line = line.strip().split(maxsplit=1)
            if not line or len(line) != 2:
                continue

            arch, startdir = line
            if arch not in arches:
                arches[arch] = []

            arches[arch].append(startdir)

        return arches

    def _generate_jobs(self, db, arches):
        assert self.id is not None, "_generate_jobs before Event.id"
        jobs = {}
        for arch in arches:
            jobs[arch] = Job(
                id=None,
                event=self,
                builder=None,
                arch=arch,
                status=AFStatus.NEW,
                tasks=arches[arch],
            )

        rows = [(self.id, arch) for arch in jobs]

        _LOGGER.info("[%s] Adding jobs to database", str(self))
        db.executemany(
            "INSERT INTO jobs (eventid, arch) VALUES (?, ?);",
            rows,
        )
        db.commit()

        cursor = db.execute(
            "SELECT arch, jobid FROM jobs WHERE eventid = ?;",
            (self.id,),
        )

        for row in cursor:
            jobs[row[0]].id = row[1]

        return jobs

    def _generate_tasks(self, db, jobs, maintainers):
        assert self.id is not None, "_generate_tasks before Event.id"

        rows = []
        for arch, job in jobs.items():
            assert job.id is not None, "_generate_tasks before Job.id"
            assert job.tasks is not None, "_generate_tasks before Job.tasks"

            for startdir in job.tasks:
                repo, pkg = startdir.split("/", maxsplit=1)
                maintainer = maintainers.get(startdir, None)
                rows.append((job.id, repo, pkg, maintainer))

        _LOGGER.info("[%s] Adding tasks to database", str(self))
        db.executemany(
            "INSERT INTO tasks (jobid, repo, pkg, maintainer) VALUES (?, ?, ?, ?);",
            rows,
        )
        db.commit()

        for job in jobs.values():
            job.tasks = Task.db_search(db, jobid=job.id)

    def db_process(self, db):
        try:
            self._db_add(db)
            self._debug_dump()
            git_init(
                self._dir, self.clone, hard=True,
                mrid=self.mrid, mrclone=self.mrclone, mrbranch=self.mrbranch,
            )
            startdirs = self._calc_startdirs()
            maintainers = self._calc_maintainers(startdirs)
            arches = self._calc_arches(startdirs)
            jobs = self._generate_jobs(db, arches)
            self._generate_tasks(db, jobs, maintainers)
        except (AssertionError, sqlite3.Error, subprocess.CalledProcessError) as e:
            _LOGGER.exception("[%s] exception:", self, exc_info=e)
            return

        for job in jobs.values():
            dispatch_queue.put(job)

@attr.s(kw_only=True, slots=True)
class Push(Event):
    type: int = attr.ib(default=AFEventType.PUSH)

    before: str = attr.ib()
    after: str = attr.ib()

    def _calc_startdirs(self):
        _LOGGER.info("[%s] Analyzing changeset", str(self))
        args = ["-p", self.target, self.before, self.after]
        startdirs = get_output("af-changes", *args, cwd=self._dir)
        startdirs = startdirs.strip().splitlines()

        return startdirs

@attr.s(kw_only=True, slots=True)
class MergeRequest(Event):
    type: int = attr.ib(default=AFEventType.MR)

    def _calc_startdirs(self):
        _LOGGER.info("[%s] Analyzing changeset", str(self))
        args = ["-m", self.target, self.revision]
        startdirs = get_output("af-changes", *args, cwd=self._dir)
        startdirs = startdirs.strip().splitlines()

        return startdirs
