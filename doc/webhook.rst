Setting up the webhook for use with GitLab
==========================================

First, create an INI file in ``/etc/abuildd`` that contains the ``[projects]``
section. The format is a list of git URI / project name key / value pairs. For
example:

.. code-block:: ini

   [projects]
   https://code.foxkit.us/sroracle/packages.git = sroracle-packages
   https://code.foxkit.us/adelie/packages.git = adelie-packages

Next, create a bare git clone for each GitLab project you would like to receive
build requests from. The name of the clone should match the name from the INI
file. Then the webhook should be run from the directory that contains the
clones. For example:

.. code-block:: console

   $ git clone --bare https://code.foxkit.us/sroracle/packages.git sroracle-packages
   $ git clone --bare https://code.foxkit.us/adelie/packages.git adelie-packages
   $ /path/to/webhook.py

The webhook can be added to a GitLab project by going to Settings > Web Hooks.
Currently, "Push Events", "Comments" (on merge requests; "notes" internally),
and "Merge Request Events" are supported.
