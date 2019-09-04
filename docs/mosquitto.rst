Using mosquitto(8) as an MQTT broker
====================================

The following options should be added to the `mosquitto.conf(5)
<https://mosquitto.org/man/mosquitto-conf-5.html>`_ file::

   password_file /path/to/mosquitto-passwd
   acl_file /path/to/mosquitto-acl

where ``mosquitto-acl`` is copied and edited from
``docs/mosquitto-acl.example``. In particular, a section must be added
to the ACL file for each builder. The ``mosquitto-passwd`` file can be
constructed using the `mosquitto_passwd(1)
<https://mosquitto.org/man/mosquitto_passwd-1.html>`_ command.
