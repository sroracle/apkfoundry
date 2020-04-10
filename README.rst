README for APK Foundry
======================

an APK-based package build orchestrator and distribution builder

:Authors:
  * **Max Rees**, maintainer
:Status:
  Alpha
:Copyright:
  © 2019-2020 Max Rees. GPL-2.0 open source licence.

Dependencies
------------

* Python 3.6+
* GitLab runner
* `apk-tools <https://gitlab.alpinelinux.org/alpine/apk-tools>`_
  (``apk.static`` only)
* `bubblewrap <https://github.com/projectatomic/bubblewrap>`_
  (installed as non-setuid)
* Linux kernel with unprivileged user namespace support
* `shadow-uidmap <https://github.com/shadow-maint/shadow>`_
* `skalibs <https://skarnet.org/software/skalibs>`_ (build-time only
  for statically-compiled helper program)
