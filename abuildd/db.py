# SPDX-License-Identifier: MIT
# Copyright (c) 2018 Max Rees
# See LICENSE for more information.
import logging  # getLogger
import sys      # exit

import asyncpg  # create_pool

from abuildd.config import GLOBAL_CONFIG

LOGGER = logging.getLogger(__name__)

async def init_pgpool(loop=None):
    kwargs = {}
    kwargs["host"] = GLOBAL_CONFIG["database"]["host"] or None
    kwargs["port"] = GLOBAL_CONFIG.getint("database", "port") or None
    kwargs["user"] = GLOBAL_CONFIG["database"]["user"] or None
    kwargs["passfile"] = GLOBAL_CONFIG["database"]["passfile"] or None
    kwargs["database"] = GLOBAL_CONFIG["database"]["name"] or None

    try:
        pgpool = await asyncpg.create_pool(loop=loop, **kwargs)
    except OSError as e:
        LOGGER.error(f"Could not connect to SQL server: {e}")
        sys.exit(10)

    return pgpool

async def db_add_job(db, job, status="new", shortmsg="", msg=""):
    job_row = await db.fetchrow(
        """INSERT INTO job(status, shortmsg, msg, priority,
        project, url, branch,
        commit_id, mr_id, username)
        VALUES($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        RETURNING job_id AS id;""",
        status, shortmsg, msg, job.priority,
        job.project, job.url, job.branch,
        job.commit, job.mr, job.user)

    job.id = job_row["id"]
    return job.id

async def db_reject_job(db, job, shortmsg, status="rejected", msg=""):
    job.priority = -1
    job_id = await db_add_job(db, job, status, shortmsg, msg)
    LOGGER.error(f"Rejecting job {job_id}: {shortmsg}")

async def db_add_task(db, job_id, package, arch):
    task_row = await db.fetchrow(
        """INSERT INTO task(job_id, package, version, arch, maintainer)
        VALUES($1, $2, $3, $4, $5)
        RETURNING task_id AS id;""",
        job_id, package.pkgname, package.pkgver, arch,
        package.maintainer[0])

    return task_row["id"]
