# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
from .gitlab import gitlab_recv_hook

HEADERS = {
    "HTTP_X_GITLAB_EVENT": "gitlab",
}

RECV_HOOKS = {
    "gitlab": gitlab_recv_hook,
}
