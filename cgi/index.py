#!/usr/bin/env python3
import cgitb  # enable
import os     # environ
from urllib.parse import parse_qsl

import apkfoundry.cgi as cgi
from apkfoundry.database import db_start

cgitb.enable()

try:
    database = db_start(readonly=True)
except Exception as e:
    cgi.error(500, "Database unavailable")

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

cgi.setenv("query", query)

if ["project"] == params:
    cgi.events_page(database, query, True)

elif ["events"] == params and query["events"]:
    query["event"] = query["events"]
    cgi.jobs_page(database, query, True)

elif ["jobs"] == params and query["jobs"]:
    query["job"] = query["jobs"]
    cgi.tasks_page(database, query, True)

elif "events" in query:
    cgi.events_page(database, query, False)

elif "jobs" in query:
    cgi.jobs_page(database, query, False)

elif "tasks" in query:
    cgi.tasks_page(database, query, False)

elif "arches" in query or params in (["arch"], ["builder"]):
    cgi.arches_page(database, query)

else:
    cgi.home_page(database)
