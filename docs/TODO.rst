Next release:

* docs: add documentation about the internal environment and scripting

Future releases:

* af-sudo needs some love.

  * Restore ability to handle multiple simultaneous connections
  * send RC as a character instead of raw bytes (ew)
  * in the future, communicate CWD

* bug? supplementary groups which aren't mapped inside the container
  aren't dropped

  * This causes the coreutils and rsync check()s to fail because they
    then think that 65534 is a valid GID to try to chgrp things to
  * `CVE-2018-7169 <https://nvd.nist.gov/vuln/detail/CVE-2018-7169>`_
    `LP#1729357 <https://bugs.launchpad.net/ubuntu/+source/shadow/+bug/1729357>`_
    `shadow!97 <https://github.com/shadow-maint/shadow/pull/97>`_
  * Due to the issues above newgidmap will set setgroups to deny iif
    invoked by a user trying to map only themselves into a new
    namespace when they have no subgid entries.

* feature: af-buildrepo: add --interactive
* feature: af_userconf/buildrepo should copy pubkey to REPODEST
  automatically?
* feature: resignapk should only re-sign new .apks
* feature: project configuration - uploading
* feature: reusing containers - detect if CDIR passed to buildrepo is
  already bootstrapped
* feature: af-buildrepo cloning with external .apkfoundry
* feature: Restore webhook server for running pipelines against other
  repos?
* bug: gl-run should use ``SYSTEM_FAILURE_EXIT_CODE`` and
  ``BUILD_FAILURE_EXIT_CODE``
