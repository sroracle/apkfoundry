README for APK Foundry
======================

an APK-based package build orchestrator and distribution builder

:Authors:
  * **Max Rees**, maintainer
:Status:
  Alpha
:Copyright:
  © 2019 Max Rees. MIT open source licence.

Synopsis
--------

* ``af-agentd``: executes build requests and publishes the artifacts to
  a central location
* ``af-dispatchd``: collect event requests and dispatches them to
  available builder agents as well as record updates from the agents

Dependencies
------------

Base set
   * Python 3.6+
   * MQTT broker
   * `attrs <http://attrs.org>`_
   * `paho.mqtt <https://github.com/eclipse/paho.mqtt.python>`_

``af-agentd``
   * `bubblewrap <https://github.com/projectatomic/bubblewrap>`_
     (installed as non-setuid)
   * `shadow-uidmap <https://github.com/shadow-maint/shadow>`_

``af-irc``
   * `PyIRC <https://code.foxkit.us/IRC/PyIRC>`_

Web interface
   * `jinja2 <http://jinja.pocoo.org>`_
