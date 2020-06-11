* QoI

  * General cleanup and refactoring
  * ``SYSTEM_FAILURE_EXIT_CODE`` vs ``BUILD_FAILURE_EXIT_CODE`` (these
    are missing the ``CUSTOM_ENV_`` prefix)

* Immediate implementation wishlist

  * resignapk should only re-sign new .apks
  * Project configuration - uploading
  * Add documentation about the internal environment and scripting
  * Reusing containers - detect if CDIR passed to buildrepo is already
    bootstrapped
  * af-buildrepo cloning with external .apkfoundry

* Long-term implementation wishlist

  * Restore webhook server for running pipelines against other repos?
