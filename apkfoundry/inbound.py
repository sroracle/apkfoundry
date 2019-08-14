# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import logging # getLogger

from . import inbound_queue, af_exit
from .gitlab import HOOKS as _GL_HOOKS

_LOGGER = logging.getLogger(__name__)

_HOOKS = {
    **_GL_HOOKS,
}

def inbound_thread():
    try:
        for eventpath, payload in inbound_queue:
            for prefix in _HOOKS:
                if eventpath.name.startswith(prefix):
                    hook = _HOOKS[prefix]
                    break
            else:
                _LOGGER.debug("[%s] no matching hook", eventpath)
                continue

            _LOGGER.info("[%s] received event from %s", eventpath, prefix)
            hook(payload)

    except Exception as e:
        _LOGGER.exception("exception:", exc_info=e)

    finally:
        _LOGGER.critical("exiting")
        af_exit()
