#!/usr/bin/env python3
import glob       # glob
import os         # environ
import setuptools # setup
from pathlib import Path

def get_path(name):
    return Path("/" + os.environ[name].strip("/"))

sysconfdir = get_path("SYSCONFDIR")
libexecdir = get_path("LIBEXECDIR")
docdir = get_path("DOCDIR")

setuptools.setup(
    scripts=glob.glob("bin/*"),
    data_files=[
        (
            str(sysconfdir),
            ["docs/abuild.conf"],
        ),
        (
            str(libexecdir),
            glob.glob("libexec/*"),
        ),
        (
            str(docdir),
            [
                *glob.glob("docs/*.rst"),
                *glob.glob("LICENSE*"),
                "README.rst",
            ],
        ),
    ]
)
