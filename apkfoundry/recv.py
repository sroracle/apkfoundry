# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import errno   # EAGAIN
import json    # load, JSONDecodeError
import logging # getLogger
import os      # open, O_NONBLOCK, O_RDONLY, read

from . import get_config, inbound_queue, af_exit, read_fifo

_LOGGER = logging.getLogger(__name__)

_EVENTDIR = get_config("dispatch").getpath("events")
_NOTIFYPATH = _EVENTDIR / "notify.fifo"

def _load_eventpath(eventpath):
    try:
        with open(eventpath, "r") as eventfile:
            payload = json.load(eventfile)
            inbound_queue.put((eventpath, payload))

    except (FileNotFoundError, PermissionError, json.JSONDecodeError) as e:
        _LOGGER.exception("[%s] exception:", eventpath, exc_info=e)

    finally:
        try:
            eventpath.unlink()
        except Exception:
            pass

def startup_flush():
    try:
        fd = os.open(_NOTIFYPATH, os.O_RDONLY | os.O_NONBLOCK)

        while True:
            txt = os.read(fd, 4096)
            if not txt:
                break

        os.close(fd)

    except OSError as e:
        if e.errno != errno.EAGAIN:
            raise

    for eventpath in _EVENTDIR.glob("*.json"):
        _load_eventpath(eventpath)

def recv():
    try:
        while True:
            txt = read_fifo(_NOTIFYPATH)
            if any(i == "0" for i in txt):
                _LOGGER.critical("received stop request")
                break

            _LOGGER.info("maybe %d new payloads", len(txt))

            for eventpath in _EVENTDIR.glob("*.json"):
                _load_eventpath(eventpath)

    except (Exception, KeyboardInterrupt) as e:
        _LOGGER.exception("exception:", exc_info=e)

    finally:
        _LOGGER.critical("exiting")
        af_exit(recv=True)
