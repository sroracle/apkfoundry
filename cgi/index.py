#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
# Copyright (c) 2019 Max Rees
# See LICENSE for more information.
import cgitb  # enable
import os     # environ
from urllib.parse import parse_qsl

import apkfoundry.cgi as cgi
from apkfoundry.objects import EType, EStatus
from apkfoundry.database import db_start

try:
    database = db_start(readonly=True)
except Exception as e:
    cgi.error(500, "Database unavailable")

if cgi.DEBUG:
    cgitb.enable()
    cgi.html_ok()
    database.set_trace_callback(print)

query = os.environ["QUERY_STRING"]
query = dict(parse_qsl(query, keep_blank_values=True))

if cgi.PRETTY and "PATH_INFO" in os.environ:
    pathinfo = os.environ["PATH_INFO"].split("/")
    page = pathinfo[1] if len(pathinfo) >= 2 else ""
    arg = pathinfo[2] if len(pathinfo) >= 3 else ""
    if page:
        query[page] = arg

params = list(query.keys())

if "limit" in query:
    try:
        int(query["limit"])
    except ValueError:
        error(400, "Invalid limit")
else:
    query["limit"] = cgi.LIMIT

if "type" in query and query["type"]:
    try:
        query["type"] = EType[query["type"]]
    except KeyError:
        error(400, "Invalid type")

if "status" in query and query["status"]:
    try:
        query["status"] = EStatus[query["status"]]
    except KeyError:
        error(400, "Invalid status")

cgi.setenv("query", query)

if ["project"] == params:
    cgi.events_page(database, query, True)

elif "events" in params and query["events"]:
    query["eventid"] = query["events"]
    del query["events"]
    cgi.jobs_page(database, query, True)

elif "jobs" in params and query["jobs"]:
    query["jobid"] = query["jobs"]
    del query["jobs"]
    cgi.tasks_page(database, query, True)

elif "tasks" in params and query["tasks"]:
    query["taskid"] = query["tasks"]
    del query["tasks"]
    cgi.artifacts_page(database, query)

elif "events" in query:
    cgi.events_page(database, query, False)

elif "jobs" in query:
    cgi.jobs_page(database, query, False)

elif "tasks" in query:
    cgi.tasks_page(database, query, False)

elif ["status"] == params:
    cgi.status_page(database, query)

else:
    cgi.home_page(database)
