********************
APK Foundry protocol
********************

Builders
--------

MQTT topic
^^^^^^^^^^

::

    builders
    /{name}
    /{arch}

The payload is either ``available`` or ``busy``.

Jobs
----

MQTT topic
^^^^^^^^^^

::

    jobs
    /{job.status}
    /{event.project}
    /{event.type}
    /{event.target or event.mrid}
    /{event.id}
    /{job.builder}
    /{job.arch}
    /{job.id}

New status
^^^^^^^^^^

::

    Clone: {event.clone}
    Revision: {event.revision}
    User: {event.user}
    Reason: {event.reason}
    Task: {task.id} {task.repo}/{task.pkg}
    Task: {task.id} {task.repo}/{task.pkg}
    ...

If the job is the child of a merge request event, there is additonally::

    MRID: {event.mrid}
    MRClone: {event.mrclone}
    MRBranch: {event.mrbranch}

Reject status
^^^^^^^^^^^^^

::

    Reason: {reason}

Start status
^^^^^^^^^^^^

Tasks are now in build order::

    Task: {task.id} {task.repo}/{task.pkg}
    Task: {task.id} {task.repo}/{task.pkg}
    ...

Cancel status
^^^^^^^^^^^^^

::

    User: {user}
    Reason: {reason}

Success status
^^^^^^^^^^^^^^

Payload is empty.

Fail status
^^^^^^^^^^^

Payload is empty.

Tasks
-----

MQTT topic
^^^^^^^^^^

::

    tasks
    /{task.status}
    /{event.project}
    /{event.type}
    /{event.target or event.mrid}
    /{event.id}
    /{job.builder}
    /{job.arch}
    /{job.id}
    /{task.repo}
    /{task.pkg}
    /{task.id}

Start status
^^^^^^^^^^^^

Payload is empty.

Reject status
^^^^^^^^^^^^^

This status is not used.

Cancel and fail statuses
^^^^^^^^^^^^^^^^^^^^^^^^

Some or all may be missing if appropriate::

    Tail: {tail}
    Tail: {tail}
    Tail: {tail}
    Tail: {tail}
    Tail: {tail}
    Artifact: {filename}
    Artifact: {filename}
    ...
    Product: {filename}
    Product: {filename}
    ...

Success status
^^^^^^^^^^^^^^

All should be present::

    Tail: {tail}
    Tail: {tail}
    Tail: {tail}
    Tail: {tail}
    Tail: {tail}
    Artifact: {filename}
    Artifact: {filename}
    ...
    Product: {filename}
    Product: {filename}
    ...
