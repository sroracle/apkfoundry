MQTT access control lists
=========================

The following users should be created:

``enqueue``
   For use by the webhook and the eventual enqueue CLI. It should have access
   to the following topics:

   * read ``builders/#``
   * read/write ``events/#``
   * read/write ``jobs/#``
   * read/write ``tasks/+``
   * read/write ``cancel/#``

   The username ``enqueue`` and password should be given as part of the MQTT
   URI in the ``enqueue.mqtt`` configuration option.

``irc``
   For use by the IRC bot. It should have access to the following topics:

   * read ``builders/#``
   * read ``events/#``
   * read ``jobs/#``
   * read ``tasks/+``
   * read/write ``cancel/#``

   The username ``irc`` and password should be given as part of the MQTT URI in
   the ``irc.mqtt`` configuration option.

``<arch>_<name>``
   For each builder, there should exist a user of the form
   ``<architecture>_<builder name>``. They should have access to the following
   topics:

   * read/write ``builders/<arch>/<name>``
   * read ``events/#``
   * read ``jobs/<arch>/<name>/+``
   * read/write ``tasks/+``
   * read ``cancel/#``

   The username ``<arch>/<name>`` and password should be given as part of the
   MQTT URI in the ``agent.mqtt`` configuration option on each builder.

Anonymous clients
   Any anonymous clients (if anonymous connections are enabled) may have access
   to the following topics:

   * read ``builders/#``
   * read ``events/#``
   * read ``jobs/#``
   * read ``tasks/+``
   * read ``cancel/#``
