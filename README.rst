README for abuildd
==================

an Alpine archive management software replacement

:Authors:
  * **William Pitcock**, original developer
  * **Max Rees**, maintainer
:Status:
  Alpha
:Copyright:
  © 2017-2018 William Pitcock and Max Rees. MIT open source licence.

Synopsis
--------

``abuildd`` contains multiple components that replaces the entire Alpine
archive management software. These are:

* ``abuildd-build``: runs a build and stages artifacts to a
  designated location
* ``abuildd-agentd``: runs as an agent and consumes MQTT messages for
  build requests
* ``abuildd-collect``: retrieves artifacts from a build server for a
  specific build
* ``abuildd-compose``: gathers all collected artifacts and composes a
  repository or distribution
* ``abuildd-enqueue``: enqueues new packages for building with
  dependency resolution
* ``abuildd-git-hook``: runs ``abuild-enqueue`` as necessary when new git
  commits are received
* ``abuildd-monitord``: a monitoring daemon which watches the MQTT server
  for feedback from the build servers
* ``abuildd-webhook``: a webhook implementation which enqueues new
  packages based on changeset notifications
* ``abuildd-status``: an ``aiohttp.web`` application which shows the
  current status of the build servers, also includes ``abuildd-webhook``

Dependencies
------------

``abuildd`` depends on a preconfigured PostgreSQL database and mqtt server, you
can use any mqtt server you wish for the task (mosquitto, rabbitmq, etc.). It
also depends on bubblewrap being installed for sandboxing the build.

Base set
   * Python 3.6+
   * PostgreSQL server
   * MQTT broker
   * `hbmqtt <https://hbmqtt.readthedocs.io/en/latest/>`_
   * `asyncpg <https://magicstack.github.io/asyncpg/current/>`_
   * `py3-abuild <https://code.foxkit.us/sroracle/py3-abuild>`_

``abuildd-webhook``, ``abuildd-status``
   * `aiohttp <https://aiohttp.readthedocs.io/en/stable/>`_

``abuildd-agentd``
   * `bubblewrap <https://github.com/projectatomic/bubblewrap>`_

``abuildd-irc``
   * `PyIRC <https://code.foxkit.us/IRC/PyIRC>`_

PPAs
----

``abuildd`` can be configured to build PPAs, as well as official repos. See
the ``abuildd-git-hook`` documentation for more details. Alternatively, a
GitLab webhook can be found in the ``abuildd.webhook`` module.
