* QoI

  * General cleanup and refactoring
  * ``SYSTEM_FAILURE_EXIT_CODE`` vs ``BUILD_FAILURE_EXIT_CODE`` (these
    are missing the ``CUSTOM_ENV_`` prefix I think)

* Immediate implementation wishlist

  * Integrate af-rootd into main process
  * Project configuration - uploading
  * Perhaps loosen the restrictions on the usage of $SUDO_APK - or
    otherwise document what they are. In general, add documentation
    about the internal environment
  * Reusing containers - detect if CDIR passed to buildrepo is already
    bootstrapped

* Long-term implementation wishlist

  * GitLab >= 12.6: external custom ``.gitlab-ci.yml`` path (other
    project)
  * Restore webhook server for running pipelines against other repos?
