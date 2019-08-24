* (project, type, arg) serialization to be done at orchestrator level,
  not builder level
  * if blocking is enabled, block project at orchestrator level until
    block is removed
  * multiple queues and priorities? event and get_nowait

* global replace ``/`` in branch by ``:``
* ``dispatch``: load jobs with status == ``new`` on startup and
  send out
* ``types``: logging dispatchd output to file based on object
* ``webhook``: rate limiting
* ``webhook``: GitLab secret token
* ``irc``: restore
