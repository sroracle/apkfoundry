#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import cgitb      # enable
import os         # chmod, environ
import stat       # S_I*
import sys        # exit, stdin
import tempfile   # NamedTemporaryFile
import shutil     # copyfileobj

from apkfoundry import get_config, write_fifo
from apkfoundry.recv_integrations import HEADERS
from apkfoundry.cgi import response

cgitb.enable()

cfg = get_config("dispatch")
eventdir = cfg.getpath("events")
remotes = cfg.getlist("remotes")

if "REMOTE_ADDR" not in os.environ:
    response(400, "text/plain")
    print("Could not determine your address")
    sys.exit(1)

if os.environ["REMOTE_ADDR"] not in remotes:
    response(403, "text/plain")
    print(f"IP {os.environ['REMOTE_ADDR']} is not authorized to submit events")
    sys.exit(1)

for header in HEADERS:
    if header in os.environ:
        prefix = HEADERS[header]
        break
else:
    response(400, "text/plain")
    print("No recognizable header found")
    sys.exit(1)

response(200, "text/plain")
print("Ok")

eventfile = tempfile.NamedTemporaryFile(
        dir=eventdir, prefix=prefix + "-", suffix=".json",
        mode="w", delete=False,
)
shutil.copyfileobj(sys.stdin, eventfile)
eventfile.close()
os.chmod(eventfile.name, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)

write_fifo("1")
