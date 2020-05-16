#!/usr/bin/env python3
import glob            # glob
import os              # environ
import distutils.core  # setup
from pathlib import Path

def get_path(name):
    return Path("/" + os.environ[name].strip("/"))

sysconfdir = get_path("SYSCONFDIR")
libexecdir = get_path("LIBEXECDIR")
docdir = get_path("DOCDIR")

distutils.core.setup(
    name="apkfoundry",
    version="0.2",
    url="https://code.foxkit.us/sroracle/apkfoundry",
    author="Max Rees",
    author_email="maxcrees@me.com",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Environment :: Console",
        "License :: OSI Approved :: GNU General Public License v2 (GPLv2)",
        "License :: OSI Approved :: MIT License",
        "Natural Language :: English",
        "Operating System :: POSIX :: Linux",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.6",
        "Topic :: Software Development :: Build Tools",
    ],
    license="GPL-2.0-only AND MIT",
    description="APK build orchestrator and distribution builder",
    long_description=Path("README.rst").read_text(),

    script_name="src/setup.py",
    packages=["apkfoundry"],

    scripts=glob.glob("bin/*"),
    data_files=[
        (
            str(sysconfdir),
            glob.glob("etc/*"),
        ),
        (
            str(libexecdir),
            glob.glob("libexec/*"),
        ),
        (
            str(docdir),
            [
                *glob.glob("docs/*"),
                *glob.glob("LICENSE*"),
                "README.rst",
            ],
        ),
    ]
)
