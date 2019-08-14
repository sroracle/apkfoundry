# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import logging
import queue
import sqlite3

from . import get_config, dispatch_queue, db_queue, af_exit, SITE_PACKAGE

SCHEMA = SITE_PACKAGE / "share" / "schema.sql"

_LOGGER = logging.getLogger(__name__)

def db_start(readonly=False):
    filename = get_config("database").getpath("filename")

    if readonly:
        filename = f"file:{filename}?mode=ro"

    db = sqlite3.connect(
        str(filename), uri=readonly,
        detect_types=sqlite3.PARSE_DECLTYPES,
    )

    if not readonly:
        with open(SCHEMA, "r") as f:
            db.executescript(f.read())

    return db

def db_thread():
    db = db_start()

    try:
        for obj in db_queue:
            obj.db_process(db)
    except Exception as e:
        _LOGGER.exception("exception:", exc_info=e)
    finally:
        _LOGGER.critical("exiting")
        af_exit()

if __name__ == "__main__":
    db_start()
