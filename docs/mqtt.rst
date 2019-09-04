MQTT access control lists
=========================

The following users should be created:

``dispatch``
   For use by the webhook and the eventual dispatch CLI. It should have
   access to the following topics:

   * read/write ``_new_job`` (internal use only)
   * read ``builders/#``
   * read/write ``jobs/#``
   * read/write ``tasks/#``

   The username ``dispatch`` and its password should be given as part of
   the ``dispatch`` section of the site configuration.

``builder-foo``
   Each builder should have access to the following topics:

   * read/write ``builders/builder-foo/#``
   * read/write ``jobs/+/+/+/+/+/builder-foo/#``
   * read/write ``tasks/+/+/+/+/+/builder-foo/#``

   The username and password should be given as part of the ``agent``
   section of the builder's site configuration. The username is a
   free-form name and can have any value that does not collide with the
   other users of the MQTT broker.

Anonymous clients
   Any anonymous clients (if anonymous connections are enabled) may have
   access to the following topics:

   * read ``builders/#``
   * read ``jobs/#``
   * read ``tasks/#``
