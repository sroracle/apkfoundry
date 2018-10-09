Getting started with abuildd
============================

abuildd configuration
---------------------

The files in the ``conf/`` directory are example configuration files for use
with abuildd. The ``INI`` files are copied to ``/etc/abuildd`` and changed as
appropriate. The names of the files and the distribution of content between
them is completely arbitrary and can be customized as you wish - the
configuration manager globs for ``/etc/abuildd/*.ini`` and reads them in sorted
order. Each configuration option is documented within the example configuration
files, along with their defaults. Configuration options are referred to as
``<section name>.<option name>``, for example ``irc.mqtt`` for the ``mqtt``
option in the ``[irc]`` section. Comments start with a semicolon (``;``) and
are not allowed on the same line as assignments. Assignments can span multiple
lines as long as the additional lines after the assignment are indented. Blank
lines are included in the assignments, and so assignments continue until the
next comment or assignment.

The ``conf/mosquitto-acl`` file is an example access control list file for use
with the `mosquitto(8) <https://mosquitto.org/>`_ MQTT broker. See the
``doc/mosquitto.rst`` file for more information.

.. code-block:: console

   # mkdir /etc/abuildd
   # cp conf/*.ini /etc/abuildd
   # $EDITOR /etc/abuildd/*.ini

MQTT configuration
------------------
See the ``doc/mqtt.rst`` file.

.. code-block:: console

   # $EDITOR $(grep -l '^;mqtt =' conf/*.ini)

Database configuration
----------------------

.. code-block:: console

   $ echo 'CREATE DATABASE abuildd;' | psql -U postgres
   $ psql -U postgres -d abuildd -f abuildd.sql
   # $EDITOR /etc/abuildd/database.ini
