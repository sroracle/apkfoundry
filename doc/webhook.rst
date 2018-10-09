Setting up the webhook for use with GitLab
==========================================

Create a bare git clone for each GitLab project you would like to receive build
requests from. The name of the clone should be the clone URI with slashes
replaced with full stops. Then the webhook should be run from the directory
that contains the clones. For example:

.. code-block:: console

   $ git clone --bare https://code.foxkit.us/sroracle/packages.git code.foxkit.us.sroracle.packages.git
   $ git clone --bare https://code.foxkit.us/adelie/packages.git code.foxkit.us.adelie.packages.git
   $ /path/to/webhook.py

The webhook can be added to a GitLab project by going to Settings > Web Hooks.
Currently, "Push Events", "Comments" (on merge requests; "notes" internally),
and "Merge Request Events" are supported.
