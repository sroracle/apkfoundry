#!/usr/bin/env python3
import glob       # glob
import os         # environ
import setuptools # setup
from pathlib import Path

def get_env(name, default):
    if name not in os.environ:
        return Path(default)
    return Path(os.environ[name].strip("/"))

prefix = get_env("PREFIX", "usr")
sysconfdir = get_env("SYSCONFDIR", "etc")
libexecdir = get_env("LIBEXECDIR", prefix / "libexec")
datarootdir = get_env("DATAROOTDIR", prefix / "share")
docdir = get_env("DOCDIR", datarootdir / "doc")

setuptools.setup(
    scripts=glob.glob("bin/*"),
    data_files=[
        (
            "/" + str(sysconfdir / "apkfoundry"),
            ["docs/abuild.conf"],
        ),
        (
            "/" + str(libexecdir / "apkfoundry"),
            glob.glob("libexec/*"),
        ),
        (
            "/" + str(docdir / "apkfoundry"),
            [
                *glob.glob("docs/*.rst"),
                *glob.glob("LICENSE*"),
                "README.rst",
            ],
        ),
    ]
)
