# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019-2020 Max Rees
# See LICENSE for more information.
import os           # environ
import subprocess   # check_call, check_output
import sys          # stderr, stdout
from pathlib import Path

import apkfoundry   # CACHEDIR

def check_call(args, **kwargs):
    args = [str(arg) for arg in args]
    sys.stdout.flush()
    sys.stderr.flush()
    return subprocess.check_call(args, **kwargs)

def get_branch(gitdir=None):
    args = ["git"]
    if gitdir:
        args += ["-C", str(gitdir)]
    args += ["branch", "--show-current"]
    return subprocess.check_output(args, encoding="utf-8").strip()

def get_branchdir(gitdir=None, branch=None):
    if not gitdir:
        gitdir = Path.cwd()
    else:
        gitdir = Path(gitdir)
    if not branch:
        branch = get_branch(gitdir)
    branch = branch.replace("/", ":")
    for i in (branch, "master"):
        path = gitdir / ".apkfoundry" / i
        if path.exists():
            return path

    raise FileNotFoundError(
        f"could not find .apkfoundry/{branch} or .apkfoundry/master"
    )

class CI_Env: # pylint: disable=too-many-instance-attributes
    prefix = "CUSTOM_ENV_"
    __slots__ = (
        "job",

        "after",
        "aportsdir",
        "arch",
        "before",
        "cdir",
        "project",
        "ref",
        "ref_slug",
        "tmp",

        "mr",
        "target_url",

        "cache",
        "srcdest",
    )

    def __init__(self):
        self.job = self["CI_JOB_ID"]

        self.after = self["CI_COMMIT_SHA"]
        self.aportsdir = Path(self["CI_PROJECT_DIR"])
        self.arch = self["AF_ARCH"]
        self.before = self["CI_COMMIT_BEFORE_SHA"]
        self.cdir = Path(self["CI_BUILDS_DIR"])
        self.project = self["CI_PROJECT_PATH_SLUG"]
        self.ref = self["CI_COMMIT_REF_NAME"]
        self.ref_slug = self.ref.replace("/", "-")
        self.tmp = Path(self["CI_PROJECT_DIR"] + ".tmp")

        if "CI_MERGE_REQUEST_ID" in self:
            self.mr = self["CI_MERGE_REQUEST_ID"]
            self.target_url = self["CI_MERGE_REQUEST_PROJECT_URL"]
            self.ref = self["CI_MERGE_REQUEST_TARGET_BRANCH_NAME"]
            self.ref_slug = self.ref.replace("/", "-")
        else:
            self.mr = None
            self.target_url = None

        self.cache = apkfoundry.CACHEDIR / "apk" / \
            f"{self['CI_PROJECT_PATH_SLUG']}.{self.ref}.{self.arch}"

        self.srcdest = apkfoundry.CACHEDIR / "src" / \
            f"{self['CI_PROJECT_PATH_SLUG']}"

    def __getitem__(self, key):
        return os.environ[self.prefix + key]

    def __setitem__(self, key, value):
        os.environ[self.prefix + key] = value

    def __delitem__(self, key):
        del os.environ[self.prefix + key]

    def __iter__(self):
        return [i for i in os.environ if i.startswith(self.prefix)]

    def __contains__(self, item):
        return self.prefix + item in os.environ

    def get(self, key, default=None):
        if key in self:
            return self[key]
        return default
