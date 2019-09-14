# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import json       # dumps, loads
import logging    # getLogger
import sqlite3    # Error, PrepareProtocol
import subprocess # CalledProcessError
import datetime as dt # datetime

import attr

from . import get_config, EStatus, EType
from . import get_output, git_init, dt_timestamp
from . import dispatch_queue

_MQTT_SKIP = {
    "mqtt_skip": True,
}

_LOGGER = logging.getLogger(__name__)
_PROJECTS_HOME = get_config("dispatch").getpath("projects")

def _mqtt_filter(attribute, value_):
    if "mqtt_skip" in attribute.metadata:
        if attribute.metadata["mqtt_skip"]:
            return False

    return True

def _normalize(cls, factory=None):
    def normalize(value):
        if isinstance(value, cls):
            return value
        if factory is not None:
            return factory(value)
        return cls(value)
    return normalize

def _json_conform(o):
    if isinstance(o, dt.datetime):
        return dt_timestamp(o)

    raise TypeError(f"Cannot conform: {type(o)}")

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
            if field == cls.__name__.lower() + "id" and hasattr(cls, "id"):
                where.append(f"{field} = :{field}")
                break

            elif field == cls.__name__.lower() and hasattr(cls, "name"):
                where.append(f"{field} = :{field}")
                break

            elif field in ("status", "type") and hasattr(cls, field):
                where.append(f"{field} & :{field} == :{field}")
                break

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

    order = query.get("order", None)
    if order in ("created", "updated"):
        sql += f" ORDER BY {order}"
    else:
        key = cls.__name__.lower() + "id"
        key = key if hasattr(classes[0], "id") else "rowid"
        sql += f" ORDER BY {key}"

    if query.get("asc", None):
        sql += " ASC"
    else:
        sql += " DESC"

    if query.get("limit", None):
        sql += " LIMIT :limit"
    if query.get("offset", None):
        sql += " OFFSET :offset"
    sql += ";"

    old_factory = db.row_factory
    db.row_factory = classes[0].from_db_row
    rows = db.execute(sql, query)
    db.row_factory = old_factory
    return rows

@attr.s(kw_only=True, slots=True)
class Arch:
    idle: bool = attr.ib(default=False)
    curr_jobs: list = attr.ib(factory=list)
    prev_job = attr.ib(default=None)

@attr.s(kw_only=True, slots=True)
class Builder:
    name: str = attr.ib()
    online: bool = attr.ib(default=False)
    arches: dict = attr.ib(factory=dict)

    updated: dt.datetime = attr.ib(default=None, metadata=_MQTT_SKIP)
    topic = attr.ib(default=None, metadata=_MQTT_SKIP)

    def __attrs_post_init__(self):
        self.topic = f"builders/{self.name}"

        for name, arch in self.arches.items():
            if isinstance(arch, Arch):
                continue
            self.arches[name] = Arch(**arch)

    def __str__(self):
        return self.topic

    @classmethod
    def db_search(cls, db):
        builders = db.execute(
            """SELECT builder, online, updated FROM builders
            WHERE builder IS NOT NULL;"""
        ).fetchall()

        for i, builder in enumerate(builders):
            builders[i] = builder = cls(
                name=builder[0],
                online=builder[1],
                updated=builder[2],
            )

            arches = db.execute(
                "SELECT arch, idle FROM arches WHERE builder = ?;",
                (builder.name,)
            )

            for (name, idle) in arches:
                arch = builder.arches[name] = Arch(
                    idle=idle,
                )

                arch.curr_jobs = list(Job.db_search(
                    db,
                    builder=builder.name,
                    arch=name,
                    status=EStatus.START,
                ))

                arch.prev_job = list(Job.db_search(
                    db,
                    builder=builder.name,
                    arch=name,
                    status=EStatus.DONE,
                    order="updated",
                    limit=1,
                ))
                arch.prev_job = arch.prev_job[0] if arch.prev_job else None

        return builders

    def db_process(self, db):
        db.execute(
            """INSERT OR IGNORE INTO builders (builder)
            VALUES (?);""",
            (self.name,),
        )

        db.execute(
            """UPDATE builders SET online = ?
            WHERE builder = ?;""",
            (self.online, self.name),
        )

        rows = [(self.name, name) for name in self.arches]
        db.executemany(
            """INSERT OR IGNORE INTO arches (builder, arch)
            VALUES (?, ?);""",
            rows,
        )

        rows = [(arch.idle, self.name, name) for name, arch in self.arches.items()]
        db.executemany(
            """UPDATE arches SET idle = ?
            WHERE builder = ? AND arch = ?;""",
            rows,
        )

        db.commit()

    def to_mqtt(self):
        payload = attr.asdict(self, recurse=True, filter=_mqtt_filter)
        payload = json.dumps(payload, default=_json_conform)
        return payload.encode("utf-8")

    @classmethod
    def from_mqtt(cls, topic, payload):
        assert topic.startswith("builders/")
        payload = payload.decode("utf-8")
        payload = json.loads(payload)

        return cls(
            **payload,
            topic=topic,
        )

@attr.s(kw_only=True, slots=True)
class Task:
    id: int = attr.ib(default=None)
    job = attr.ib() # Job or int
    repo: str = attr.ib()
    pkg: str = attr.ib()
    maintainer: str = attr.ib(default=None)
    tail: str = attr.ib(default=None)
    status = attr.ib(default=EStatus.NEW, converter=_normalize(EStatus))

    created: dt.datetime = attr.ib(
        default=dt.datetime.min,
        converter=_normalize(dt.datetime, dt.datetime.utcfromtimestamp)
    )
    updated: dt.datetime = attr.ib(default=None, metadata=_MQTT_SKIP)

    dir = attr.ib(default=None, metadata=_MQTT_SKIP)
    _topic = attr.ib(default=None, metadata=_MQTT_SKIP)
    _tables = ("tasks", "tasks_full")

    def __str__(self):
        return self.topic

    def __setattr__(self, name, value):
        if name not in ("topic", "_topic"):
            self._topic = None
        super().__setattr__(name, value)

    @property
    def topic(self):
        if self._topic is not None:
            return self._topic

        if isinstance(self.job, int):
            job_topic = f"@/@/@/@/@/@/{self.job}"
        else:
            job_topic = self.job.topic
            job_topic = "/".join(job_topic.split("/")[2:])

        self._topic = "/".join((
            "tasks",
            str(self.status),
            job_topic,
            self.repo,
            self.pkg,
            str(self.id) if self.id else "@",
        ))

        return self._topic

    @topic.setter
    def topic(self, value):
        self._topic = value

    @property
    def startdir(self):
        return f"{self.repo}/{self.pkg}"

    def to_mqtt(self):
        payload = attr.asdict(self, recurse=False, filter=_mqtt_filter)
        if not isinstance(payload["job"], int):
            payload["job"] = payload["job"].id
        payload = json.dumps(payload, default=_json_conform)
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
            WHERE taskid = ?;""",
            (self.status, self.tail, self.id),
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
            status=EStatus(row[5]),
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
    status = attr.ib(default=EStatus.NEW, converter=_normalize(EStatus))
    tasks = attr.ib(default=None)
    payload = attr.ib(default=None)

    created: dt.datetime = attr.ib(
        default=dt.datetime.min,
        converter=_normalize(dt.datetime, dt.datetime.utcfromtimestamp)
    )
    updated: dt.datetime = attr.ib(default=None, metadata=_MQTT_SKIP)

    dir = attr.ib(default=None, metadata=_MQTT_SKIP)
    _topic = attr.ib(default=None, metadata=_MQTT_SKIP)
    _tables = ("jobs", "jobs_full")

    def __str__(self):
        return self.topic

    def __setattr__(self, name, value):
        if name not in ("topic", "_topic"):
            self._topic = None
        super().__setattr__(name, value)

    @property
    def topic(self):
        if self._topic is not None:
            return self._topic

        if isinstance(self.event, int):
            event_topic = f"@/@/@/{self.event}"
        else:
            event_topic = self.event.topic
            event_topic = "/".join(event_topic.split("/")[2:])

        self._topic = "/".join((
            "jobs",
            str(self.status),
            event_topic,
            self.builder or "@",
            self.arch,
            str(self.id) if self.id else "@",
        ))

        return self._topic

    @topic.setter
    def topic(self, value):
        self._topic = value

    def to_mqtt(self, recurse=False):
        payload = attr.asdict(self, recurse=recurse, filter=_mqtt_filter)
        if not recurse:
            if not isinstance(payload["event"], int):
                payload["event"] = payload["event"].id

            payload["tasks"] = [
                i if isinstance(i, int) else i.id \
                for i in payload["tasks"]
            ]

        payload = json.dumps(payload, default=_json_conform)
        return payload.encode("utf-8")

    @classmethod
    def from_mqtt(cls, topic, payload):
        assert topic.startswith("jobs/")
        payload = payload.decode("utf-8")
        payload = json.loads(payload)

        job = cls(
            **payload,
            topic=topic,
        )

        if isinstance(job.event, dict):
            job.event = Event(**job.event)

        if (isinstance(job.tasks, list)
                and all(isinstance(task, dict) for task in job.tasks)):
            job.tasks = [Task(**task) for task in job.tasks]

        return job

    @classmethod
    def from_db_row(cls, cursor_, row):
        return cls(
            id=row[0],
            event=row[1],
            builder=row[2],
            arch=row[3],
            status=EStatus(row[4]),
            created=row[5],
            updated=row[6],
        )

    def db_process(self, db):
        if self.status == EStatus.START:
            db.execute(
                "UPDATE jobs SET builder = ?, status = ? WHERE jobid = ?;",
                (self.builder, self.status, self.id),
            )

        if self.status & EStatus.ERROR:
            db.execute(
                "UPDATE tasks SET status = ? WHERE jobid = ? AND status = 1;",
                (self.status, self.id),
            )

        db.commit()

    @classmethod
    def db_search(cls, db, where=None, **query):
        return _db_search((cls, Event), db, where, **query)

@attr.s(kw_only=True, slots=True)
class Event:
    id: int = attr.ib(default=None)
    project: str = attr.ib()
    type: int = attr.ib(default=EType.PUSH, converter=_normalize(EType))
    clone: str = attr.ib()
    target: str = attr.ib()
    revision: str = attr.ib()
    user: str = attr.ib()
    reason: str = attr.ib()
    status = attr.ib(default=EStatus.NEW, converter=_normalize(EStatus))
    mrid: int = attr.ib(default=None)
    mrclone: str = attr.ib(default=None)
    mrbranch: str = attr.ib(default=None)

    created: dt.datetime = attr.ib(
        default=dt.datetime.min,
        converter=_normalize(dt.datetime, dt.datetime.utcfromtimestamp)
    )
    updated: dt.datetime = attr.ib(default=None, metadata=_MQTT_SKIP)

    _dir = attr.ib(default=None, metadata=_MQTT_SKIP)
    _topic = attr.ib(default=None, metadata=_MQTT_SKIP)
    _tables = ("events",)

    def __attrs_post_init__(self):
        self._dir = _PROJECTS_HOME / self.project

    def __str__(self):
        return self.topic

    def __setattr__(self, name, value):
        if name not in ("topic", "_topic"):
            self._topic = None
        super().__setattr__(name, value)

    @property
    def topic(self):
        if self._topic is not None:
            return self._topic

        self._topic = "/".join((
            "events",
            str(self.status),
            self.project,
            str(self.type),
            self.target,
            str(self.id) if self.id else "@",
        ))
        return self._topic

    @topic.setter
    def topic(self, value):
        self._topic = value

    @classmethod
    def from_db_row(cls, cursor_, row):
        return cls(
            id=row[0],
            project=row[1],
            type=EType(row[2]),
            clone=row[3],
            target=row[4],
            revision=row[5],
            user=row[6],
            reason=row[7],
            status=EStatus(row[8]),
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
        cursor = db.execute(
            "SELECT created FROM events WHERE eventid = ?;",
            (self.id,),
        )
        (self.created,) = cursor.fetchone()

    def _debug_dump(self):
        _LOGGER.debug("[%s] Clone: %s", str(self), self.clone)
        _LOGGER.debug("[%s] Revision: %s", str(self), self.revision)
        _LOGGER.debug("[%s] User: %s", str(self), self.user)
        _LOGGER.debug("[%s] Reason: %s", str(self), self.reason)

    def _calc_startdirs(self):
        raise NotImplementedError

    def _calc_maintainers(self, startdirs):
        _LOGGER.info("[%s] Retrieving maintainers", str(self))
        startdirs = [i + "/APKBUILD" for i in startdirs]
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
            "af-arch", self.target,
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
        if not arches:
            _LOGGER.info("No jobs generated!")
            return {}

        rows = [(self.id, arch) for arch in arches]

        _LOGGER.info("[%s] Adding jobs to database", str(self))
        db.executemany(
            "INSERT INTO jobs (eventid, arch) VALUES (?, ?);",
            rows,
        )
        db.commit()

        jobs = Job.db_search(db, eventid=self.id)
        jobs = {job.arch: job for job in jobs}
        for job in jobs.values():
            job.event = self
            job.tasks = arches[job.arch]

        return jobs

    def _generate_tasks(self, db, jobs, maintainers):
        assert self.id is not None, "_generate_tasks before Event.id"

        if not jobs:
            return

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
            job.tasks = list(Task.db_search(db, jobid=job.id))

    def db_process(self, db):
        try:
            self._db_add(db)
            self._debug_dump()
            git_init(
                self._dir, self.clone,
                rev=self.revision,
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
    type: int = attr.ib(default=EType.PUSH)

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
    type: int = attr.ib(default=EType.MR)

    def _calc_startdirs(self):
        _LOGGER.info("[%s] Analyzing changeset", str(self))
        args = ["-m", self.target, self.revision]
        startdirs = get_output("af-changes", *args, cwd=self._dir)
        startdirs = startdirs.strip().splitlines()

        return startdirs
