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

Jobs
----

MQTT topic
^^^^^^^^^^

::

    jobs
    /{job.status}
    /{event.project}
    /{event.type}
    /{event.target}
    /{event.id}
    /{job.builder}
    /{job.arch}
    /{job.id}

Tasks
-----

MQTT topic
^^^^^^^^^^

::

    tasks
    /{task.status}
    /{event.project}
    /{event.type}
    /{event.target}
    /{event.id}
    /{job.builder}
    /{job.arch}
    /{job.id}
    /{task.repo}
    /{task.pkg}
    /{task.id}
