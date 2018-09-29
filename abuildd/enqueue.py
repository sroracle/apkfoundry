import asyncio   # CancelledError, Condition, ensure_future
import fnmatch   # fnmatchcase
import json      # dumps, loads, JSONDecodeError
import logging   # getLogger, basicConfig
import shlex     # quote
import sys       # exit
import functools # partial

from abuild.config import SHELLEXPAND_PATH
from abuild.file import APKBUILD
from hbmqtt.mqtt.constants import QOS_1, QOS_2

from abuildd.connections import init_pgpool, init_mqtt
from abuildd.config import GLOBAL_CONFIG
from abuildd.utility import get_command_output, run_blocking_command
from abuildd.utility import assert_exists

logger = logging.getLogger(__name__)
logger.setLevel("DEBUG")
logging.basicConfig(format='%(asctime)-15s %(levelname)s %(message)s')

SHELLEXPAND_PATH = shlex.quote(str(SHELLEXPAND_PATH))
DEFAULT_PRIORITY = 500

def priorityspec(entries):
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

class ArchCollection(dict):
    def __init__(self, *args, loop=None, **kwargs):
        self.any_available = asyncio.Condition(loop=loop)
        return super().__init__(*args, **kwargs)

class Job:
    def __init__(self, event, project, config, url, branch, commit, user):
        self.event = event
        self.project = project
        self.config = config
        self.url = url
        self.branch = branch
        self.commit = commit
        self.user = user

        self.id = None
        self.tasks = []
        self.mr = 0

        self.priority = self.config.getint(self.event, "priority")

    async def get_packages(self):
        raise NotImplementedError

    async def analyze_packages(self):
        self.packages = dict.fromkeys(self.packages)

        for package in self.packages:
            contents = await get_command_output(
                ["git", "-C", self.project, "show",
                f"{self.commit}:{package}/APKBUILD"])

            expanded = await self.loop.run_in_executor(
                None, APKBUILD, package, contents)

            self.packages[package] = expanded.meta

        return self.packages

    def user_priority(self):
        allowed_users = self.config[self.event]["allowed_users"].split("\n")
        allowed_users = priorityspec(allowed_users)
        denied_users = self.config[self.event]["denied_users"].split("\n")

        if allowed_users:
            for pattern in allowed_users:
                if fnmatch.fnmatchcase(self.user, pattern):
                    return allowed_users[pattern]

            return -1

        for pattern in denied_users:
            if fnmatch.fnmatchcase(self.user, pattern):
                return -1

        return DEFAULT_PRIORITY

    async def calc_priority(self, db):
        # TODO: add a setting for project priority

        if self.priority < 0:
            await db_reject_job(db, self, "Invalid priority")
            return

        user_priority = self.user_priority()
        if user_priority < 0:
            await db_reject_job(
                db, self, "Unauthorized user or invalid priority")
            return
        self.priority += user_priority

        branch_priority = DEFAULT_PRIORITY
        if hasattr(self, "branch_priority"):
            branch_priority = self.branch_priority()
            if branch_priority < 0:
                await db_reject_job(
                    db, self, "Unauthorized branch or invalid priority")
                return
        self.priority += branch_priority

    async def enqueue(self, db, mqtt, builders):
        await self.get_packages()
        try:
            await self.analyze_packages()
        except RuntimeError as e:
            await db_reject_job(db, self, e)
            return

        async with db.transaction():
            await self.calc_priority(db)
            if self.priority < 0:
                return

            await db_add_job(db, self)

        # Collect all needed arches first. It is possible that there are
        # intra-job dependencies (between different tasks of a single job) and
        # thus we want to send all tasks of this job to one build server for
        # each arch involved.
        all_arches = {}
        for package in self.packages:
            arches = self.packages[package]["arch"]
            if "all" in arches or "noarch" in arches:
                arches += self.config["builders"]["arches"].split("\n")
            all_arches.update({arch: None for arch in arches})

        # Get build server for each arch
        for arch in all_arches:
            if arch.startswith("!") or arch == "all" or arch == "noarch":
                continue

            # Use ensure_future so that we can keep going - there might
            # be no builders available for this arch, but there might be
            # some for the next arch!
            all_arches[arch] = asyncio.ensure_future(choose_builder(builders, arch))

        for package in self.packages:
            package = self.packages[package]
            arches = package["arch"]

            for arch in arches:
                if arch.startswith("!") or "!" + arch in arches:
                    continue
                if arch == "all" or arch == "noarch":
                    continue

                task_id = await db_add_task(db, self.id, package, arch)
                task = {
                    "task_id": task_id, "job_id": self.id,
                    "event": self.event, "priority": self.priority,
                    "project": self.project, "url": self.url,
                    "branch": self.branch, "commit": self.commit,
                    "package": package["pkgname"], "mr_id": self.mr,
                }
                task = json.dumps(task).encode("utf-8")

                builder = all_arches[arch]

                # Again, don't block here - the builder may still not be
                # available yet
                asyncio.ensure_future(
                    mqtt_send_task(mqtt, builder, arch, self.id, task_id, task))

class PushJob(Job):
    def __init__(self, *args, **kwargs):
        super().__init__("push", *args, **kwargs)

        self.before = None
        self.after = self.commit

    async def get_packages(self):
        # TODO: need to handle before == None
        filenames = []
        self.packages = []

        await run_blocking_command(
            ["git", "-C", self.project, "fetch", "origin",
            f"{self.branch}:{self.branch}"])
        filenames = await get_command_output(
            ["git", "-C", self.project, "diff-tree", "-r", "--name-only",
            "--diff-filter", "d", f"{self.before}..{self.after}"])

        for filename in filenames.split("\n"):
            if filename.endswith("APKBUILD"):
                self.packages.append(filename.replace("/APKBUILD", "", 1))

        logger.debug(
            f"[{self.project}] Push {self.after}: " + " ".join(self.packages))
        return self.packages

    def branch_priority(self):
        branches = priorityspec(self.config["push"]["branches"].split("\n"))

        if not branches:
            return DEFAULT_PRIORITY

        for pattern in branches:
            if fnmatch.fnmatchcase(self.branch, pattern):
                return branches[pattern]

        return -1

class MRJob(Job):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.target = None

    async def get_packages(self):
        filenames = []
        self.packages = []

        await run_blocking_command(
            ["git", "-C", self.project, "fetch", "origin",
            f"{self.target}:{self.target}"])
        await run_blocking_command(
            ["git", "-C", self.project, "fetch", self.url,
            f"{self.branch}:mr-{self.mr}"])
        base = await get_command_output(
            ["git", "-C", self.project, "merge-base", self.target,
            f"mr-{self.mr}"])
        filenames = await get_command_output(
            ["git", "-C", self.project, "diff-tree", "-r", "--name-only",
            "--diff-filter", "d", f"{base}..{self.commit}"])

        for filename in filenames.split("\n"):
            if filename.endswith("APKBUILD"):
                self.packages.append(filename.replace("/APKBUILD", "", 1))

        logger.debug(
            f"[{self.project}] Merge #{self.mr}: " + " ".join(self.packages))
        return self.packages

async def init_conns(loop=None):
    logger.info("Initializing connections...")

    pgpool = await init_pgpool(loop=loop)
    mqtt = await init_mqtt([["builders/#", QOS_1]], loop=loop)

    logger.info("Done!")
    return (pgpool, mqtt)

async def db_add_job(db, job, status="unbuilt", msg=""):
    job_row = await db.fetchrow("""
INSERT INTO job(status, msg, priority, project, url, branch,
            commit_id, mr_id, username)
VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9)
RETURNING job_id AS id;""",
          status, msg, job.priority, job.project, job.url, job.branch,
          job.commit, job.mr, job.user)

    job.id = job_row["id"]
    return job.id

async def db_add_task(db, job_id, package, arch):
    task_row = await db.fetchrow("""
INSERT INTO task(job_id, package, version, arch, maintainer)
VALUES($1, $2, $3, $4, $5)
RETURNING task_id AS id;""",
          job_id, package["pkgname"], package["pkgver"], arch,
          package["maintainer"][0])

    return task_row["id"]

async def db_reject_job(db, job, msg):
    job.priority = -1
    job_id = await db_add_job(db, job, "rejected", msg)
    logger.error(f"Rejecting job {job_id}: {msg}")

async def mqtt_send_task(mqtt, builder, arch, job_id, task_id, task):
    await builder
    builder = builder.result()
    logger.debug(f"Sending #{job_id}/{task_id} to {arch} builder {builder}")
    await mqtt.publish(f"tasks/{arch}/{builder}/{task_id}", task, QOS_2)

async def mqtt_watch_servers(mqtt, builders):
    while True:
        try:
            message = await mqtt.deliver_message()
            # builders/<arch>/<name>
            topic = message.topic.split("/")
            if len(topic) != 3:
                logger.error(f"Invalid builder topic {message.topic}")
                continue

            arch = topic[1]
            name = topic[2]

            try:
                data = json.loads(message.data)
            except json.JSONDecodeError:
                logger.error(
                    f"JSON decode error for MQTT data '{message.data}'"
                    f"on topic {message.topic}")
                continue

            data["name"] = name

            try:
                assert_exists(data, "nprocs", int)
                assert_exists(data, "ram_mb", int)
                assert_exists(data, "status", str)
            except JSONDecodeError as e:
                logger.error(f"MQTT payload: {e.msg}")
                continue

            status = data["status"]
            data["pref"] = calc_builder_preference(data)

            if arch not in builders:
                logger.error(f"Arch '{arch}' is not enabled")
                continue

            arch_collection = builders[arch]

            if name not in arch_collection:
                logger.info(f"{arch} builder {name} joined ({status})")

            elif arch_collection[name]["status"] != status:
                logger.info(f"{arch} builder {name} becomes {status}")

            async with arch_collection.any_available:
                arch_collection[name] = data

                if status == "idle":
                    arch_collection.any_available.notify()

                elif not get_avail_builders(builders, arch):
                    logger.warning(f"No builders available for {arch}")

        except asyncio.CancelledError:
            break

def get_avail_builders(builders, arch):
    return [i for i in builders[arch].values() if i["status"] == "idle"]

def calc_builder_preference(builder):
    c_proc = GLOBAL_CONFIG.getfloat("builders", "coeff_proc")
    c_ram = GLOBAL_CONFIG.getfloat("builders", "coeff_ram")

    pref = int(c_proc * builder["nprocs"] + c_ram * builder["ram_mb"])

    return pref

async def choose_builder(builders, arch):
    async with builders[arch].any_available:
        avail = get_avail_builders(builders, arch)
        while not avail:
            await builders[arch].any_available.wait()
            avail = get_avail_builders(builders, arch)

        avail.sort(key=lambda x: x["pref"], reverse=True)
        builder = avail[0]
        builder["status"] = "busy"

    return builder["name"]

