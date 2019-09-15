# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import errno   # EAGAIN
import json    # load, JSONDecodeError
import logging # getLogger
import os      # open, O_NONBLOCK, O_RDONLY, read

from . import get_config, af_exit, read_fifo
from .recv_integrations import RECV_HOOKS

_LOGGER = logging.getLogger(__name__)

_CFG = get_config("dispatch")
_EVENTDIR = _CFG.getpath("events")
_NOTIFYPATH = _EVENTDIR / "notify.fifo"
_KEEP_EVENTS = _CFG.getboolean("keep_events")

def process_eventfile(eventfile):
    try:
        with open(eventfile, "r") as f:
            payload = json.load(f)

        for prefix in RECV_HOOKS:
            if eventfile.name.startswith(prefix + "-"):
                hook = RECV_HOOKS[prefix]
                break
        else:
            _LOGGER.debug("[%s] no matching hook", eventfile)
            return

        _LOGGER.info("[%s] received event from %s", eventfile, prefix)
        hook(payload)

    except Exception as e:
        _LOGGER.exception("[%s] exception:", eventfile, exc_info=e)

    finally:
        if _KEEP_EVENTS:
            return

        try:
            eventfile.unlink()
        except Exception as e:
            _LOGGER.warning("[%s] failed to delete: %s", eventfile, e)

def startup_flush():
    try:
        fd = os.open(_NOTIFYPATH, os.O_RDONLY | os.O_NONBLOCK)

        while True:
            txt = os.read(fd, 4096)
            if not txt:
                break

        os.close(fd)

    except FileNotFoundError:
        os.mkfifo(_NOTIFYPATH, mode=0o660)

    except OSError as e:
        if e.errno != errno.EAGAIN:
            raise

    for eventfile in _EVENTDIR.glob("*.json"):
        process_eventfile(eventfile)

def recv():
    try:
        while True:
            txt = read_fifo(_NOTIFYPATH)
            if any(i == "0" for i in txt):
                _LOGGER.critical("received stop request")
                break
            if all(i != "1" for i in txt):
                continue

            _LOGGER.info("maybe %d new payloads", len(txt))

            for eventfile in _EVENTDIR.glob("*.json"):
                process_eventfile(eventfile)

    except (Exception, KeyboardInterrupt) as e:
        _LOGGER.exception("exception:", exc_info=e)

    finally:
        _LOGGER.critical("exiting")
        af_exit(recv=True)
