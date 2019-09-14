# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import logging # getLogger
import json    # dumps
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from .. import get_config, EStatus

_LOGGER = logging.getLogger(__name__)
_WEB_CFG = get_config("web")
_WEB_BASE = _WEB_CFG["base"]
_WEB_PRETTY = _WEB_CFG["pretty"]

def af_to_gitlab_status(status):
    if status == EStatus.NEW:
        return "pending"
    if status == EStatus.START:
        return "running"
    if status == EStatus.CANCEL:
        return "canceled"
    if status == EStatus.SUCCESS:
        return "success"

    return "failed"

def gitlab_post_hook(job):
    try:
        config = get_config(job.event.clone)
    except KeyError:
        _LOGGER.error("[%s] unknown project", job.event.clone)
        return

    if not config["gitlab_token"]:
        _LOGGER.debug("[%s] no gitlab_token, skipping integration", job)
        return
    gl_token = config["gitlab_token"]
    if not config["gitlab_endpoint"]:
        _LOGGER.debug("[%s] no gitlab_endpoint, skipping integration", job)
        return
    gl_url = config["gitlab_endpoint"].rstrip("/")
    gl_url += f"/statuses/{job.event.revision}"

    if _WEB_PRETTY:
        af_url = _WEB_BASE.rstrip("/") + f"/jobs/{job.id}"
    else:
        af_url = _WEB_BASE + f"?jobs={job.id}"

    if job.event.mrbranch:
        ref = job.event.mrbranch
    else:
        ref = job.event.target

    payload = {
        "name": f"AF: {job.arch}",
        "state": af_to_gitlab_status(job.status),
        "target_url": af_url,
        "ref": ref,
    }

    request = Request(
        url=gl_url,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Private-Token": gl_token,
        },
        data=json.dumps(payload).encode("utf-8"),
    )

    _LOGGER.info("[%s] Posting status to GitLab", job)

    try:
        urlopen(request)
    except HTTPError as e:
        _LOGGER.error("[%s] GitLab responded with error: %s", job, e)
    else:
        _LOGGER.info("[%s] Posted status to GitLab", job)
