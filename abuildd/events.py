# SPDX-License-Identifier: MIT
# Copyright (c) 2018 Max Rees
# See LICENSE for more information.
import asyncio    # get_event_loop
import fnmatch    # fnmatchcase
import json       # dumps
import logging    # getLogger, basicConfig
import shlex      # quote
import traceback  # format_exc

from hbmqtt.mqtt.constants import QOS_2
from abuild.config import SHELLEXPAND_PATH
from abuild.file import APKBUILD
import abuild.exception as exc

import abuildd.tasks  # pylint: disable=cyclic-import
from abuildd.utility import get_command_output, run_blocking_command
from abuildd.utility import assert_exists

_LOGGER = logging.getLogger(__name__)

SHELLEXPAND_PATH = shlex.quote(str(SHELLEXPAND_PATH))
DEFAULT_PRIORITY = 500
FAKE_COMMIT_ID = "0000000000000000000000000000000000000000"

# c.f. abuildd.sql event_category_enum
EVENT_CATEGORIES = (
    "push",
    "merge_request",
    "note",
    "irc",
    "manual",
)

def _priorityspec(entries):
    d = {}

    if entries == [""]:
        return d

    for entry in entries:
        entry = entry.split(":", maxsplit=1)
        if len(entry) == 1:
            d[entry[0]] = DEFAULT_PRIORITY
        else:
            d[entry[0]] = int(entry[1])

    return d

class Event:
    __slots__ = (
        "id", "category", "status", "shortmsg", "msg",
        "project", "url", "branch", "commit", "user",

        "_loop", "_config", "_packages", "_priority",
        "_jobs",
    )

    # pylint: disable=redefined-builtin
    def __init__(self, *, category, project, url, branch, commit, user,
                 id=None, status="new", shortmsg="", msg="", loop=None,
                 config=None):
        self.id = id
        self.category = category
        self.status = status
        self.shortmsg = shortmsg
        self.msg = msg
        self.project = project
        self.url = url
        self.branch = branch
        self.commit = commit
        self.user = user

        if loop is not None:
            self._loop = loop
        else:
            self._loop = asyncio.get_event_loop()

        self._packages = {}
        self._config = config
        self._priority = None
        self._jobs = None

    @classmethod
    def fromGLWebhook(cls, project, config, payload, loop=None):
        raise NotImplementedError

    @staticmethod
    def validate_dict(data):
        if not isinstance(data, dict):
            raise ValueError("data must be of type dict")

        assert_exists(data, "id", int)
        assert_exists(data, "category", str)
        assert_exists(data, "status", str)
        assert_exists(data, "shortmsg", str)
        assert_exists(data, "msg", str)
        assert_exists(data, "project", str)
        assert_exists(data, "url", str)
        assert_exists(data, "branch", str)
        assert_exists(data, "commit", str)
        assert_exists(data, "user", str)

        if data["status"] not in abuildd.tasks.STATUSES:
            raise ValueError("Invalid status")

    @classmethod
    def from_dict(cls, data):
        cls.validate_dict(data)
        return cls(**data)

    @classmethod
    def from_dict_abs(cls, data):
        category = assert_exists(data, "category", str)
        if category == "push":
            inst = PushEvent.from_dict(data)
        elif category == "merge_request":
            inst = MREvent.from_dict(data)
        elif category == "note":
            inst = NoteEvent.from_dict(data)
        else:
            raise ValueError(f"Invalid category {category}")

        return inst

    def to_dict(self):
        return {slot: getattr(self, slot) for slot in self.__slots__
                if not slot.startswith("_")}

    async def db_add(self, db):
        mr_id = getattr(self, "mr_id", 0)

        event_row = await db.fetchrow(
            """INSERT INTO event(category, status, shortmsg, msg,
            project, url, branch,
            commit_id, mr_id, username)
            VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            RETURNING id;""",
            self.category, self.status, self.shortmsg, self.msg,
            self.project, self.url, self.branch,
            self.commit, mr_id, self.user)

        self.id = event_row["id"]

    def set_status(self, status, shortmsg="", msg=""):
        self.status = status
        self.shortmsg = shortmsg
        self.msg = msg

    async def db_update(self, db, status, shortmsg="", msg=""):
        if not self.id:
            raise RuntimeError("Event hasn't been added yet")

        self.set_status(status, shortmsg, msg)

        await db.fetchrow(
            """UPDATE event
            SET status = $1, shortmsg = $2, msg = $3
            WHERE id = $4""",
            self.status, self.shortmsg, self.msg,
            self.id)

    async def reject(self, db, mqtt, shortmsg, msg=""):
        self.set_status("rejected", shortmsg, msg)
        self._priority = -1
        await self.db_add(db)
        await self.mqtt_send(mqtt)
        _LOGGER.error(f"Rejecting event #{self.id}: {self.shortmsg}")

    async def mqtt_send(self, mqtt):
        dump = json.dumps(self.to_dict()).encode("utf-8")
        await mqtt.publish(f"events/{self.category}/{self.id}", dump, QOS_2)

    async def get_packages(self):
        raise NotImplementedError

    async def analyze_packages(self):
        for package in self._packages:
            contents = await get_command_output(
                ["git", "-C", self.project, "show",
                 f"{self.commit}:{package}/APKBUILD"])

            try:
                expanded = await self._loop.run_in_executor(
                    None, APKBUILD, package, contents)
            except exc.abuildException as e:
                e.msg = f"{package}: {e.msg}"
                raise

            self._packages[package] = expanded

        return self._packages

    def user_priority(self):
        allowed_users = self._config[self.category]["allowed_users"].split("\n")
        allowed_users = _priorityspec(allowed_users)
        denied_users = self._config[self.category]["denied_users"].split("\n")

        if allowed_users:
            for pattern in allowed_users:
                if fnmatch.fnmatchcase(self.user, pattern):
                    return allowed_users[pattern]

            return -1

        for pattern in denied_users:
            if fnmatch.fnmatchcase(self.user, pattern):
                return -1

        return DEFAULT_PRIORITY

    async def calc_priority(self, db, mqtt):
        if self._priority is not None:
            return self._priority

        # TODO: add a setting for project priority
        self._priority = self._config.getint(self.category, "priority")

        if self._priority < 0:
            await self.reject(db, mqtt, "Invalid priority")
            return -1

        user_priority = self.user_priority()
        if user_priority < 0:
            await self.reject(
                db, mqtt, "Unauthorized user or invalid priority")
            return -1
        self._priority += user_priority

        branch_priority = DEFAULT_PRIORITY
        if hasattr(self, "branch_priority"):
            branch_priority = self.branch_priority()  # pylint: disable=no-member
            if branch_priority < 0:
                await self.reject(
                    db, mqtt, "Unauthorized branch or invalid priority")
                return -1
        self._priority += branch_priority

        return self._priority

    async def get_jobs(self, db, mqtt):
        if self._jobs is not None:
            return self._jobs
        self._jobs = {}

        await self.get_packages()
        try:
            await self.analyze_packages()
        except exc.abuildException as e:
            await self.reject(db, mqtt, str(e), traceback.format_exc())
            return

        if self._priority is None:
            await self.calc_priority(db, mqtt)
            if self._priority < 0:
                return

        await self.db_add(db)
        await self.mqtt_send(mqtt)

        enabled_arches = self._config["builders"]["arches"].split("\n")

        for package in self._packages:
            package = self._packages[package]

            arches = package.arch.copy()
            if "all" in arches or "noarch" in package.arch:
                arches += enabled_arches

            for arch in package.arch:
                if arch.startswith("!"):
                    arch = arch.lstrip("!")
                    if arch in arches:
                        arches = [a for a in arches if a != arch]

            for arch in arches:
                if arch.startswith("!") or arch == "all" or arch == "noarch":
                    continue

                if arch not in enabled_arches:
                    _LOGGER.warning(
                        f"{package.pkgname}: skipping disabled arch {arch}")
                    continue

                if arch not in self._jobs:
                    self._jobs[arch] = abuildd.tasks.Job(
                        event_id=self.id, priority=self._priority, arch=arch,
                        event=self)
                    await self._jobs[arch].db_add(db)

                task = abuildd.tasks.Task.from_APKBUILD(
                    self._jobs[arch].id, package)
                await task.db_add(db)
                self._jobs[arch].add_task(task)

        return self._jobs

class PushEvent(Event):
    __slots__ = ("before", "after")

    def __init__(self, *, before, after, **kwargs):
        super().__init__(**kwargs)
        self.before = before
        self.after = after

    def to_dict(self):
        d = {slot: getattr(self, slot) for slot in self.__slots__}
        d.update({slot: getattr(self, slot) for slot in super().__slots__
                  if not slot.startswith("_")})
        return d

    @staticmethod
    def validate_dict(data):
        Event.validate_dict(data)
        assert_exists(data, "before", str)
        assert_exists(data, "after", str)

    @classmethod
    def fromGLWebhook(cls, project, config, payload, loop=None):
        before = assert_exists(payload, "before", str)
        after = assert_exists(payload, "after", str)
        branch = assert_exists(payload, "ref", str)
        url = assert_exists(payload, "repository/git_http_url", str)
        user = assert_exists(payload, "user_email", str)

        if before == FAKE_COMMIT_ID:
            before = None

        if after == FAKE_COMMIT_ID:
            _LOGGER.debug(f"[{project}] Skipping push for deleted ref {branch}")
            return None

        if not branch.startswith("refs/heads/"):
            _LOGGER.debug(f"[{project}] Skipping push for non-branch ref {branch}")
            return None
        branch = branch.replace("refs/heads/", "", 1)

        _LOGGER.info(f"[{project}] Push: {branch} {before}..{after}")

        event = {
            "loop": loop,
            "project": project,
            "config": config,
            "category": "push",
            "url": url,
            "branch": branch,
            "commit": after,
            "user": user,
            "before": before,
            "after": after,
        }

        return cls(**event)

    def branch_priority(self):
        branches = _priorityspec(self._config["push"]["branches"].split("\n"))

        if not branches:
            return DEFAULT_PRIORITY

        for pattern in branches:
            if fnmatch.fnmatchcase(self.branch, pattern):
                return branches[pattern]

        return -1

    async def get_packages(self):
        # TODO: need to handle before == None
        filenames = []

        await run_blocking_command(
            ["git", "-C", self.project, "fetch", "origin",
             f"{self.branch}:{self.branch}"])
        filenames = await get_command_output(
            ["git", "-C", self.project, "diff-tree", "-r", "--name-only",
             "--diff-filter", "d", f"{self.before}..{self.after}"])

        for filename in filenames.split("\n"):
            if filename.endswith("APKBUILD"):
                self._packages[filename.replace("/APKBUILD", "", 1)] = None

        pkg_list = " ".join(self._packages.keys())
        _LOGGER.debug(f"[{self.project}] Push {self.after}: {pkg_list}")

        return self._packages

class MREvent(Event):
    __slots__ = ("mr_id", "target")

    def __init__(self, *, mr_id, target, **kwargs):
        super().__init__(**kwargs)
        self.mr_id = mr_id
        self.target = target

    def to_dict(self):
        d = {slot: getattr(self, slot) for slot in self.__slots__}
        d.update({slot: getattr(self, slot) for slot in super().__slots__
                  if not slot.startswith("_")})
        return d

    @staticmethod
    def validate_dict(data):
        Event.validate_dict(data)
        assert_exists(data, "mr_id", int)
        assert_exists(data, "target", str)

    @classmethod
    def fromGLWebhook(cls, project, config, payload, loop=None):
        event = MREvent._fromGLWebhook(project, config, payload, loop)
        if not event:
            return None

        return cls(**event)

    @staticmethod
    def _fromGLWebhook(project, config, payload, loop, note=False):
        if note:
            root = "merge_request"
        else:
            root = "object_attributes"
            state = assert_exists(payload, f"{root}/state", str)

            if state not in ("opened", "reopened"):
                # Specifically we don't care about state == closed. I'm not sure
                # if there are other states possible.
                _LOGGER.debug(f"[{project}] Skipping merge event with state {state}")
                return None

        mr_id = assert_exists(payload, f"{root}/iid", int)
        # GitLab 8: force pushes to MRs do not update the merge-request/x/head refs
        url = assert_exists(payload, f"{root}/source/http_url", str)
        branch = assert_exists(payload, f"{root}/source_branch", str)
        target = assert_exists(payload, f"{root}/target_branch", str)
        commit = assert_exists(payload, f"{root}/last_commit/id", str)
        user = assert_exists(payload, "user/username", str)

        if note:
            word = "Note"
            category = "note"
        else:
            word = "Merge"
            category = "merge_request"

        _LOGGER.info(f"[{project}] {word} #{mr_id}: up to {commit} -> {target}")

        event = {
            "loop": loop,
            "project": project,
            "config": config,
            "category": category,
            "url": url,
            "branch": branch,
            "commit": commit,
            "user": user,
            "mr_id": mr_id,
            "target": target,
        }

        return event

    async def get_packages(self):
        filenames = []

        await run_blocking_command(
            ["git", "-C", self.project, "fetch", "origin",
             f"{self.target}:{self.target}"])
        await run_blocking_command(
            ["git", "-C", self.project, "fetch", self.url,
             f"{self.branch}:mr-{self.mr_id}"])
        base = await get_command_output(
            ["git", "-C", self.project, "merge-base", self.target,
             f"mr-{self.mr_id}"])
        filenames = await get_command_output(
            ["git", "-C", self.project, "diff-tree", "-r", "--name-only",
             "--diff-filter", "d", f"{base}..{self.commit}"])

        for filename in filenames.split("\n"):
            if filename.endswith("APKBUILD"):
                self._packages[filename.replace("/APKBUILD", "", 1)] = None

        pkg_list = " ".join(self._packages.keys())
        _LOGGER.debug(f"[{self.project}] Merge #{self.mr_id}: {pkg_list}")

        return self._packages

class NoteEvent(MREvent):
    @classmethod
    def fromGLWebhook(cls, project, config, payload, loop=None):
        note_type = assert_exists(payload, "object_attributes/noteable_type", str)
        if note_type != "MergeRequest":
            _LOGGER.debug(f"[{project}] Skipping note with type {note_type}")
            return None

        content = assert_exists(payload, "object_attributes/note", str)
        if config["note"]["keyword"] not in content:
            return None

        event = MREvent._fromGLWebhook(project, config, payload, loop, note=True)
        if not event:
            return None

        return cls(**event)
