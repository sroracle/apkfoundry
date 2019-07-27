# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import email
import email.message
import email.policy
import enum
import functools
import logging
import sqlite3
import subprocess
from datetime import datetime
from typing import List

from attr import attrs, attrib

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

AFPolicy = email.policy.EmailPolicy(
    max_line_length=None,
    linesep="\n",
    raise_on_defect=False,
    mangle_from_=False,
    utf8=True,
    refold_source="None",
)

AFPayload = functools.partial(
    email.message.EmailMessage,
    policy=AFPolicy,
)

AFParser = functools.partial(
    email.message_from_bytes,
    policy=AFPolicy,
)

_ORDERINGS = {
    "id-asc": "ORDER BY id ASC",
    "asc": "ORDER BY updated ASC, id ASC",
    "id-desc": "ORDER BY id DESC",
    "desc": "ORDER BY updated DESC, id DESC",
}

_LOGGER = logging.getLogger(__name__)

_PROJECTS_HOME = get_config("dispatch").getpath("projects")

def validate_schema(schema, dct):
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
                validate_schema(value[0], i)

        elif descend and type(dct[key]) == dict:
            validate_schema(value, dct[key])

        elif descend:
            assert dct[key] == value, f"{key} must equal {value}"

class JSONSchema:
    __slots__ = ("full_schema",)

    def __init__(self, **kwargs) -> None:
        self.full_schema = {}

        for cls in self.__class__.__mro__:
            if cls.__name__ in ("object", "JSONSchema"):
                continue

            if hasattr(cls, "schema"):
                self.full_schema.update(cls.schema)

        validate_schema(self.full_schema, kwargs)

        for key in self.full_schema:
            setattr(self, key, kwargs[key])

    def __getitem__(self, key: str):
        return getattr(self, key)

    def __setitem__(self, key: str, value) -> None:
        setattr(self, key, value)

    def __delitem__(self, key) -> None:
        self.__delattr__(key)

    def __iter__(self) -> str:
        yield from self.__slots__

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    def to_dict(self) -> dict:
        return {key: self[key] for key in self.full_schema}

@attrs(kw_only=True, slots=True)
class Task:
    id: int = attrib(default=None)
    job = attrib() # Job or int
    repo: str = attrib()
    pkg: str = attrib()
    maintainer: str = attrib(default=None)
    status: int = attrib()
    tail: str = attrib()
    artifacts = attrib(default=None)

    created: datetime = attrib(default=None)
    updated: datetime = attrib(default=None)

    def __attrs_post_init__(self) -> None:
        assert self.status in AFStatus, f"Invalid task status {self.status}"

    def __str__(self) -> str:
        return self.topic()

    def topic(self, inner: bool=False) -> str:
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

    def db_process(self, db: sqlite3.Connection) -> None:
        db.execute(
            """UPDATE tasks SET status = ?, tail = ?
            WHERE job = ? AND repo = ? AND pkg = ?;""",
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
        full = False

        if where is None:
            where = []

        if query.get("id", None):
            where.append("id = :id")
        if query.get("job", None):
            where.append("job = :job")
        if query.get("repo", None):
            where.append("repo GLOB :repo")
        if query.get("pkg", None):
            where.append("pkg GLOB :pkg")
        if query.get("maintainer", None):
            where.append("IFNULL(maintainer, 'None') GLOB :maintainer")
        if query.get("status", None):
            where.append("status = :status")
        if query.get("builder", None):
            full = True
            where.append("IFNULL(builder, 'None') GLOB :builder")
        if query.get("arch", None):
            full = True
            where.append("arch GLOB :arch")
        if query.get("event", None):
            full = True
            where.append("event = :event")
        if query.get("project", None):
            full = True
            where.append("project GLOB :project")
        if query.get("type", None):
            full = True
            where.append("type = :type")
        if query.get("clone", None):
            full = True
            where.append("clone GLOB :clone")
        if query.get("target", None):
            full = True
            where.append("target GLOB :target")
        if query.get("mrid", None):
            full = True
            where.append("mrid = :mrid")
        if query.get("mrclone", None):
            full = True
            where.append("mrclone GLOB :mrclone")
        if query.get("mrbranch", None):
            full = True
            where.append("mrbranch GLOB :mrbranch")
        if query.get("user", None):
            full = True
            where.append("user GLOB :user")

        if full:
            sql = f"SELECT * FROM taskfull"
        else:
            sql = f"SELECT * FROM tasks"

        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " " + _ORDERINGS.get(
            query.get("order", None), _ORDERINGS["desc"],
        )

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

@attrs(kw_only=True, slots=True)
class Job:
    id: int = attrib(default=None)
    event = attrib() # Event or int
    builder: str = attrib(default=None)
    arch: str = attrib()

    created: datetime = attrib(default=None)
    updated: datetime = attrib(default=None)

    tasks = attrib(default=None)
    payload = attrib(default=None)
    dir = attrib(default=None)

    _status = attrib(default=None)
    _topic = attrib(default=None)

    def __attrs_post_init__(self) -> None:
        assert self.status in AFStatus, f"Invalid job status {self.status}"

    def __str__(self) -> str:
        return self.topic

    @property
    def topic(self, inner: bool=False) -> str:
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

        return "/".join((
            *prefix,
            event_topic,
            self.builder or "@",
            self.arch,
            str(self.id) if self.id else "@",
        ))

    @topic.setter
    def topic(self, value):
        self._topic = value

    @property
    def status(self) -> AFStatus:
        return self._status

    @status.setter
    def status(self, value):
        self._status = value
        self._topic = None
        self.topic

    def to_mqtt(self, user="", reason=""):
        self.payload = payload = AFPayload()
        if self.status == AFStatus.NEW:
            payload["Clone"] = self.event.clone
            payload["Revision"] = self.event.revision
            payload["User"] = self.event.user
            payload["Reason"] = self.event.reason

            if self.event.type == AFEventType.MR:
                payload["MRID"] = self.event.mrid
                payload["MRClone"] = self.event.mrclone
                payload["MRBranch"] = self.event.mrbranch

            for task in self.tasks:
                payload["Task"] = f"{task} {self.tasks[task]}"

        elif self.status == AFStatus.REJECT:
            payload["Reason"] = reason

        elif self.status == AFStatus.START:
            for task in self.tasks:
                payload["Task"] = f"{task} {self.tasks[task]}"

        elif self.status == AFStatus.CANCEL:
            payload["User"] = user
            payload["Reason"] = reason

        else:
            pass

        return payload.as_string()

    @classmethod
    def from_mqtt(cls, topic, payload):
        assert topic.startswith("jobs/")

        args = topic.split("/", maxsplit=8)
        return cls(
            status=AFStatus[args[1]],
            event=int(args[5]) if args[5] != "@" else None,
            builder=args[6] if args[6] != "@" else None,
            arch=args[7],
            id=int(args[8]) if args[8] != "@" else None,
            topic=topic,

            payload=AFParser(payload),
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
            tasks=[],
        )

    def db_process(self, db: sqlite3.Connection) -> None:
        db.execute(
            "UPDATE jobs SET builder = ?, status = ? WHERE id = ?;",
            (self.builder, self.status, self.id),
        )

        if self.status & (AFStatus.START | AFStatus.DONE):
            db.execute(
                "UPDATE tasks SET status = ? WHERE job = ? AND status = 'new';",
                (self.status, self.id),
            )

        db.commit()

    @classmethod
    def db_search(cls, db, where=None, **query):
        full = False
        if where is None:
            where = []

        if query.get("id", None):
            where.append("id = :id")
        if query.get("event", None):
            where.append("event = :event")
        if query.get("builder", None):
            where.append("IFNULL(builder, 'None') GLOB :builder")
        if query.get("arch", None):
            where.append("arch GLOB :arch")
        if query.get("status", None):
            where.append("status = :status")
        if query.get("project", None):
            full = True
            where.append("project GLOB :project")
        if query.get("type", None):
            full = True
            where.append("type = :type")
        if query.get("clone", None):
            full = True
            where.append("clone GLOB :clone")
        if query.get("target", None):
            full = True
            where.append("target GLOB :target")
        if query.get("mrid", None):
            full = True
            where.append("mrid = :mrid")
        if query.get("mrclone", None):
            full = True
            where.append("mrclone GLOB :mrclone")
        if query.get("mrbranch", None):
            full = True
            where.append("mrbranch GLOB :mrbranch")
        if query.get("user", None):
            full = True
            where.append("user GLOB :user")

        if full:
            sql = "SELECT * FROM jobfull"
        else:
            sql = "SELECT * FROM jobs"

        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " " + _ORDERINGS.get(
            query.get("order", None), _ORDERINGS["desc"],
        )

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

@attrs(kw_only=True, slots=True)
class Event:
    id: int = attrib(default=None)
    project: str = attrib()
    type: int = attrib()
    clone: str = attrib()
    target: str = attrib()
    mrid: int = attrib(default=None)
    mrclone: str = attrib(default=None)
    mrbranch: str = attrib(default=None)
    revision: str = attrib()
    user: str = attrib()
    reason: str = attrib()
    status: int = attrib()

    created: datetime = attrib(default=None)
    updated: datetime = attrib(default=None)

    _dir = attrib(default=None)
    _startdirs = attrib(default=None)
    _arches = attrib(default=None)
    _jobs = attrib(default=None)
    _maintainers = attrib(default=None)

    def __attrs_post_init__(self) -> None:
        assert self.status in AFStatus, f"Invalid event status {self.status}"
        assert self.type in AFEventType, f"Invalid event type {self.type}"
        self._dir = _PROJECTS_HOME / self.project

    def __str__(self) -> str:
        return self.topic()

    def topic(self, inner: bool=False) -> str:
        if inner:
            prefix = ()
        else:
            prefix = ("events", str(self.status))

        return "/".join((
            *prefix,
            self.project,
            str(self.type),
            self.mrid if self.type == AFEventType.MR else self.target,
            str(self.id) if self.id else "@",
        ))

    @classmethod
    def from_db_row(cls, cursor_, row):
        return cls(
            id=row[0],
            project=row[1],
            type=AFEventType(row[2]),
            clone=row[3],
            target=row[4],
            mrid=row[5],
            mrclone=row[6],
            mrbranch=row[7],
            revision=row[8],
            user=row[9],
            reason=row[10],
            status=AFStatus(row[11]),
            created=row[12],
            updated=row[13],
        )

    @classmethod
    def db_search(cls, db, where=None, **query):
        if where is None:
            where = []

        if query.get("id", None):
            where.append("id = :id")
        if query.get("project", None):
            where.append("project GLOB :project")
        if query.get("user", None):
            where.append("user GLOB :user")
        if query.get("type", None):
            where.append("type = :type")
        if query.get("clone", None):
            where.append("clone GLOB :clone")
        if query.get("target", None):
            where.append("target GLOB :target")
        if query.get("mrid", None):
            where.append("mrid = :mrid")
        if query.get("mrclone", None):
            where.append("mrclone GLOB :mrclone")
        if query.get("mrbranch", None):
            where.append("mrbranch GLOB :mrbranch")
        if query.get("status", None):
            where.append("status = :status")

        sql = "SELECT * FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " " + _ORDERINGS.get(
            query.get("order", None), _ORDERINGS["desc"],
        )

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

    def _db_add(self, db: sqlite3.Connection) -> None:
        assert self.id is None, "_db_add after self.id"
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

    def _debug_dump(self) -> None:
        _LOGGER.debug("[%s] Clone: %s", str(self), self.clone)
        _LOGGER.debug("[%s] Revision: %s", str(self), self.revision)
        _LOGGER.debug("[%s] User: %s", str(self), self.user)
        _LOGGER.debug("[%s] Reason: %s", str(self), self.reason)

    def _git_init(self) -> None:
        raise NotImplementedError

    def _calc_startdirs(self) -> None:
        raise NotImplementedError

    def _calc_maintainers(self) -> None:
        _LOGGER.info("[%s] Retrieving maintainers", str(self))
        self._maintainers = get_output(
            "af-maintainer", *self._startdirs, cwd=self._dir,
        )
        self._maintainers = self._maintainers.strip().splitlines()
        self._maintainers = [line.split(maxsplit=1) for line in self._maintainers]
        self._maintainers = {line[0]: line[1] for line in self._maintainers if line}

    def _calc_arches(self) -> None:
        _LOGGER.info("[%s] Generating architecture list", str(self))
        lines = get_output(
            "af-arch", "-b", self.target,
            *self._startdirs, cwd=self._dir,
        ).strip().splitlines()

        self._arches = {}
        for line in self._arches:
            line = line.strip().split(maxsplit=1)
            if not line or len(line) != 2:
                continue

            arch, startdir = line
            if arch not in self._arches:
                self._arches[arch] = []

            self._arches[arch].append(startdir)

        self._startdirs = None

    def _generate_jobs(self, db: sqlite3.Connection) -> List[Job]:
        assert self.id is not None, "_generate_jobs before self.id"
        self._jobs = {}
        for arch in self._arches:
            self._jobs[arch] = Job(
                id=None,
                event=self,
                builder=None,
                arch=arch,
                status=AFStatus.NEW,
                tasks=self._arches[arch],
            )
        self._arches = None

        rows = [(self.id, arch) for arch in self._jobs]

        _LOGGER.info("[%s] Adding jobs to database", str(self))
        db.executemany(
            "INSERT INTO jobs (event, arch) VALUES (?, ?);",
            rows,
        )
        db.commit()

        cursor = db.execute(
            "SELECT arch, id FROM jobs WHERE event = ?;",
            (self.id,),
        )

        for row in cursor:
            self._jobs[row[0]].id = row[1]

    def _generate_tasks(self, db: sqlite3.Connection) -> None:
        assert self.id is not None, "_generate_tasks before self.id"
        assert self._jobs is not None, "_generate_tasks before self._jobs"

        rows = []
        for arch in self._jobs:
            job = self._jobs[arch]
            assert job.id is not None, "_generate_tasks before job.id"
            assert job.tasks is not None, "_generate_tasks before job.tasks"
            for startdir in job.tasks:
                repo, pkg = startdir.split("/", maxsplit=1)
                maintainer = self._maintainers.get(startdir, None)
                rows.append((job.id, repo, pkg, maintainer))

        _LOGGER.info("[%s] Adding tasks to database", str(self))
        db.executemany(
            "INSERT INTO tasks (job, repo, pkg, maintainer) VALUES (?, ?, ?, ?);",
            rows,
        )
        db.commit()

        for arch in self._jobs:
            job = self._jobs[arch]

            cursor = db.execute(
                "SELECT repo, pkg, id FROM tasks WHERE job = ?;",
                (job.id,),
            )

            job.tasks = {f"{row[0]}/{row[1]}": row[2] for row in cursor}

    def db_process(self, db: sqlite3.Connection) -> None:
        try:
            self._db_add(db)
            self._debug_dump()
            git_init(
                self._dir, self.clone, hard=True,
                mrid=self.mrid, mrclone=self.mrclone, mrbranch=self.mrbranch,
            )
            self._calc_startdirs()
            self._calc_maintainers()
            self._calc_arches()
            self._generate_jobs(db)
            self._generate_tasks(db)
        except (AssertionError, sqlite3.Error, subprocess.CalledProcessError) as e:
            _LOGGER.exception("[%s] exception:", self, exc_info=e)
            return

        for arch in self._jobs:
            dispatch_queue.put(self._jobs[arch])

@attrs(kw_only=True, slots=True)
class Push(Event):
    type: int = attrib(default=AFEventType.PUSH)

    before: str = attrib()
    after: str = attrib()

    def _calc_startdirs(self) -> None:
        _LOGGER.info("[%s] Analyzing changeset", str(self))
        args = ["-p", self.target, self.before, self.after]
        self._startdirs = get_output("af-changes", *args, cwd=self._dir)
        self._startdirs = self._startdirs.strip().splitlines()

@attrs(kw_only=True, slots=True)
class MergeRequest(Event):
    type: int = attrib(default=AFEventType.MR)

    def _calc_startdirs(self) -> None:
        _LOGGER.info("[%s] Analyzing changeset", str(self))
        args = ["-m", self.mrid, self.target, self.revision]
        self._startdirs = get_output("af-changes", *args, cwd=self._dir)
        self._startdirs = self._startdirs.strip().splitlines()
