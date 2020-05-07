* Bugs

  * bootstrapping without the widest coverage of repos leads to "package
    not found" errors later when switching repositories - related to
    updating / upgrading

* Documentation

  * Make note of disabling the "Auto-cancel redundant, pending
    pipelines" option

* QoI

  * General cleanup and refactoring
  * ``SYSTEM_FAILURE_EXIT_CODE`` vs ``BUILD_FAILURE_EXIT_CODE`` (these
    are missing the ``CUSTOM_ENV_`` prefix I think)

* Immediate implementation wishlist

  * Project configuration

    * Repository ordering and architecture coverage
    * Logging strategies - copy log for each package to separate file,
      or exclusively log to separate file, or only one log
    * Updating / upgrading
    * Uploading

* Long-term implementation wishlist

  * GitLab >= 12.6: external custom ``.gitlab-ci.yml`` path (other
    project)
  * Restore webhook server for running pipelines against other repos?
