* Project configuration

  * What to do after build failure
  * Tee build logs for each package, or exclusively log to separate
    file, or only one log to rule them all
* Builder configuration

  * Deletion policy
* Distfiles cache
* BUG: bootstrapping without the widest coverage of repos leads to
  "package not found" errors later when switching repositories

* Documentation

  * Make note of disabling the "Auto-cancel redundant, pending pipelines" option
* ``af-req-root`` - needs to be suffixed by architecture?

* gitlab-runner issues

  * remove ``/tmp/custom-executor*``
* checkapk needs to distinguish ``$APK and ``$APK_FETCH``, or otherwise
  rootd needs to accept what it'll send
* ``SYSTEM_FAILURE_EXIT_CODE`` vs ``BUILD_FAILURE_EXIT_CODE`` (these are
  missing the ``CUSTOM_ENV_`` prefix I think)

* Code cleanup
* GitLab >= 12.6: external custom ``.gitlab-ci.yml`` path (other
  project)

  * Restore separate ``.apkfoundry`` as an option
