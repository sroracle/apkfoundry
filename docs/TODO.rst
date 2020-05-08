* QoI

  * General cleanup and refactoring
  * ``SYSTEM_FAILURE_EXIT_CODE`` vs ``BUILD_FAILURE_EXIT_CODE`` (these
    are missing the ``CUSTOM_ENV_`` prefix I think)

* Immediate implementation wishlist

  * Project configuration - uploading
  * Perhaps loosen the restrictions on the usage of $SUDO_APK - or
    otherwise document what they are. In general, add documentation
    about the internal environment
  * Reusing containers - detect if CDIR passed to buildrepo is already
    bootstrapped
  * Make it easier to open container as root
    * setgid /af/info and make sure the files are writable by group
  * Remove dependency on abuild-rmtemp (in progress)

* Long-term implementation wishlist

  * GitLab >= 12.6: external custom ``.gitlab-ci.yml`` path (other
    project)
  * Restore webhook server for running pipelines against other repos?
