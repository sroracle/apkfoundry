# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
from .gitlab import gitlab_post_hook

JOB_POST_HOOKS = (
    gitlab_post_hook,
)
