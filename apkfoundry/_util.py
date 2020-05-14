# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019-2020 Max Rees
# See LICENSE for more information.
import pwd          # getpwnam
import subprocess   # check_call, check_output
import sys          # stderr, stdout
from pathlib import Path

import apkfoundry # APK_STATIC

def check_call(args, **kwargs):
    args = [str(arg) for arg in args]
    sys.stdout.flush()
    sys.stderr.flush()
    return subprocess.check_call(args, **kwargs)

def get_arch():
    return subprocess.check_output(
        [apkfoundry.APK_STATIC, "--print-arch"],
        encoding="utf-8",
    ).strip()

def get_branch(gitdir=None):
    args = ["git"]
    if gitdir:
        args += ["-C", str(gitdir)]
    args += ["branch", "--show-current"]
    return subprocess.check_output(args, encoding="utf-8").strip()

def get_branchdir(gitdir=None, branch=None):
    if not branch:
        branch = get_branch(gitdir)
    if not gitdir:
        gitdir = Path.cwd()
    else:
        gitdir = Path(gitdir)
    branch = branch.replace("/", ":")
    for i in (branch, "master"):
        path = gitdir / ".apkfoundry" / i
        if path.exists():
            return path

    raise FileNotFoundError(
        f"could not find .apkfoundry/{branch} or .apkfoundry/master"
    )

def rootid():
    return pwd.getpwnam("af-root")
