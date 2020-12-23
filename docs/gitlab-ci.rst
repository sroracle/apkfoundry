*******************************
GitLab CI configuration details
*******************************

When running on the APK Foundry executor, there are a few notes to take
into account:

* The ``script:`` key is run within the container once for each package
  to be built. The working directory is set to the git repository root
  (``/af/aports``), and ``$1`` is set to the startdir that needs to be
  built currently (e.g. ``system/debianutils``).
* Due to how executors are implemented in GitLab runner,
  ``before_script:`` is run from the same shell script as ``script:``,
  and thus is run once per package build inside the container with
  ``/af/aports`` as the working directory.
* ``after_script:`` is run regardless of the success of all the package
  builds, from a separate shell script inside the container after they
  all have been attempted.
* Stage job, and tag names are all completely arbitrary.
* Since GitLab runner only allows uploading artifacts from within
  ``GIT_CLONE_PATH``, a symlink ``.gl-repos`` is provided in the git
  repository root pointing to ``REPODEST`` for your convenience.
* Don't enable shallow cloning unless you know what you're doing! It
  could prevent APK Foundry from determining what to build for a job.
* **Make sure to disable the "Auto-cancel redundant, pending pipelines"
  option!** Otherwise, builds may get canceled before they complete just
  because a new push has been made to the repository.

Variables
---------

================== =====================================================
     Variable                              Notes
================== =====================================================
``CI_BUILDS_DIR``  This is the directory root for the container. Inside
                   the container it will be ``/``.
``GIT_CLONE_PATH`` This must be set to ``$CI_BUILDS_DIR/af/aports``.
``AFCI_PROJ_CONF`` Where to find the APK Foundry project configuration.
                   Can be specified as a git clone URL from which to
                   fetch it, or a clone URL and a branch separated by
                   spaces. Leave unset or blank to use the default of
                   ``.apkfoundry/`` relative to the project's git root
                   on the current branch.
``AFCI_ARCH``      The architecture for which this job will build.
``AFCI_PACKAGES``  Whitespace-delimited list of packages to manually
                   include in the build, in the format ``repo/pkg``.
``AFCI_MANUAL``    Only consider ``AFCI_PACKAGES``; do not scan the
                   revision range for change APKBUILDs. Can be any
                   non-empty value to signify "yes".
``AFCI_AFTERDIR``  Whether to mount the project's ``after`` script
                   configuration directory (located in
                   ``$AF_CONFIG/after/$project``) for this job. Can be
                   any non-empty value to signify "yes". Note that this
                   will most likely cause things such as re-signing of
                   ``.apk`` files and syncing to remote hosts to occur.
================== =====================================================

Example configuration files:

* `GitLab Runner (TOML) <docs/examples/gitlab-runner-config.toml>`_
* `GitLab CI (YAML) <docs/examples/gitlab-ci.yml>`_
* `Build script (shell) <docs/examples/build.sh>`_
* `After script (shell) <docs/examples/after.sh>`_
* `After script configuration (shell) <docs/examples/after-config.sh>`_
