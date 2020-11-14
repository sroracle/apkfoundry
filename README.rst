**********************
README for APK Foundry
**********************

an APK-based package build orchestrator and distribution builder

:Authors:
  **Max Rees**, maintainer
:Status:
  Beta
:Releases and source code:
  `Foxkit Code Syndicate <https://code.foxkit.us/sroracle/apkfoundry>`_
:Copyright:
  © 2018-2020 Max Rees. GPL-2.0 & MIT open source licences.

Dependencies
------------

* Python 3.6+
* `bubblewrap <https://github.com/containers/bubblewrap>`_ (installed as
  non-setuid)
* Linux kernel with unprivileged user namespace support (preferably >=
  4.15 because < 4.15 has limited ID mapping)
* `shadow-uidmap <https://github.com/shadow-maint/shadow>`_
* Build-time dependency: C compiler and libc headers suitable for static
  binary compilation

* GitLab runner (optional - supported integration)

Getting started
---------------

See `the quickstart guide <docs/quickstart.rst>`_.

Installing
----------

See `the installation guide <docs/install.rst>`_.
