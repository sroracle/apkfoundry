***************************
APK Foundry release history
***************************

Unreleased
----------

Added
^^^^^

* The dependency graph generator now warns if STARTDIRs are masked by
  ``arch=`` or ``options=!libc_*`` in the APKBUILDs.
* The new project configuration option ``build.only-changed-versions``
  was added to only trigger revision-based builds when ``pkgver=`` or
  ``pkgrel=`` change in the APKBUILDs.
* ``af-buildrepo`` gained the ``-o``/``--config-option`` option to allow
  overriding project configuration options on the command line.
* The new project configuration option ``build.networking`` was added to
  unconditionally allow networking access in all package builds instead
  of only when ``options=net`` is specified in the APKBUILDs.
* ``checkapk`` now has two additional modes of operation: comparing two
  entirely local ``.apk`` files, and comparing one new local ``.apk``
  file with a remote old one.

Breaking changes
^^^^^^^^^^^^^^^^

* The ``AF_PRIVKEY``, ``AF_PRIVKEY_B64``, and ``AF_PUBKEY`` CI
  environment variables are no longer used. All users should migrate to
  using an ``after`` script. For more information, see
  `the configuration guide <docs/configuration.rst>`_.

Deprecated
^^^^^^^^^^

* The ``-s``/``--srcdest`` CLI options were renamed to ``--cache-src``
  for ``af-buildrepo`` and ``af-mkchroot``. The ``-s``/``--srcdest``
  aliases **will be dropped in a future release**.
* The ``-c``/``--cache`` CLI options were renamed to ``--cache-apk`` for
  ``af-buildrepo`` and ``af-mkchroot``. The ``-c``/``--cache`` aliases
  **will be dropped in a future release**.
* The ``-A`` short CLI option for ``af-buildrepo`` and ``af-mkchroot``
  is deprecated and **will be dropped in a future release**. Use
  ``--arch``.
* The ``-S`` short CLI option for ``af-buildrepo`` and ``af-mkchroot``
  is deprecated and **will be dropped in a future release**. Use
  ``--setarch``.
* The ``-r`` short CLI option for ``af-mkchroot`` is deprecated and
  **will be dropped in a future release**. Use ``--repodest``.
* The ``-r`` short CLI option for ``af-chroot`` is deprecated and **will
  be dropped in a future release**. Use ``--repo``.
* The ``--script`` CLI option was renamed to ``--build-script`` for
  ``af-buildrepo``. The ``--script`` alias **will be dropped in a future
  release**.
* The site-local configuration now has ``container.subuid`` and
  ``container.subgid`` to replace ``container.subid``, which assumed
  both were the same. The old ``container.subid`` continues to be
  supported in this release (setting both new values) with a warning
  that support **will be dropped in a future release**.
* All project configuration option names have changed in order to be
  more organized. The old names ("v1") continue to be supported in this
  release with a warning that support **will be dropped in a future
  release**.
* All CI environment variables starting with ``AF_`` have been renamed
  to the ``AFCI_`` namespace to avoid namespace clashing. For the new
  variable names, see `the CI guide <docs/gitlab-ci.rst>`_. The old
  names **will be dropped in a future release**.

Other changes
^^^^^^^^^^^^^

* It is clearer when cloning ``.apkfoundry`` configuration via
  ``AF_PROJ_CONFIG`` is occurring now that it has its own section which
  shows what the ``HEAD`` commit of the clone is.

Fixed
^^^^^

* The ``af_abuild`` shell wrapper now dies with a nonzero exit code if
  check_arch or check_libc fails instead of returning zero. This allows
  whole trees of dependent packages to be pruned if their ancestors are
  masked by ``arch=`` or ``options=!libc_*`` in the APKBUILDs.
  Recommended for use with ``build.on-failure=recalculate`` (formerly
  ``on_failure``).
* The dependency graph generator now only checks for repositories
  configured in ``repo.arch`` (formerly ``repos``).
* The dependency graph generator now correctly handles APKBUILD
  ``provides=`` that contain colons or complex version constraints.
* The dependency graph generator now sorts and deduplicates warnings for
  unknown dependencies.
* The usage text for the ``af-rmchroot`` CLI utility was corrected.
* Documentation for the ``AF_BRANCHDIR`` environment variable was added.
* The logging section functionality for Gitlab was fixed so that time
  spent in each section is now accurate instead of always zero seconds.
* ``checkapk`` now has clearer error messages when ``.apk`` downloads
  fail.
* ``resignapk`` now handles relative paths for ``-k`` and ``-p``
  correctly.
* ``checkapk`` now correctly prints filenames that contain spaces.

0.6 - 2020-11-14
----------------

Added
^^^^^

* The ``persistent_repodest`` project configuration option was added for
  ease-of-use when building branches.
* ``af-buildrepo`` gained the ``-i``/``--interactive`` option for
  interactively handling build failures.
* The Gitlab plugin now logs when it is using re-signing keys.

Breaking changes
^^^^^^^^^^^^^^^^

* The interposition with ``abuild`` now uses ``ABUILD_TMP`` instead of
  ``ABUILD_SRCDIR`` and ``ABUILD_PKGBASEDIR``.
* The temporary containers for use with Gitlab are now named with a
  prefix of ``gl-job-{job_number}-`` and a suffix of ``.af``.
* The temporary containers made by ``af-buildrepo`` are now suffixed
  with ``.af``.

Other changes
^^^^^^^^^^^^^

* The build logic now automatically changes directory to the correct
  STARTDIR, removing the need to add ``cd "$APORTSDIR/$1"`` to build
  scripts.
* The ``af_userconf`` shell function now automatically copies any
  configured or temporary public key to ``/etc/apk/keys``.

Fixed
^^^^^

* ``/etc/hosts`` and ``/etc/resolv.conf`` are no longer bind-mounted
  directly into the root filesystem, which would cause problems if the
  container's ``apk`` detected that they were unchanged relative to
  their parent package (it would try to overwrite them, and fail).
* The example bootstrap script now uses ``ln`` with the ``-f`` option.
* ``af-buildrepo`` now ensures that all temporary files are deleted when
  ``--dry-run`` is given.
* The path in which ``AF_PRIVKEY`` keys are located was corrected in the
  documentation.
* A bug that made it impossible to use ``AF_PRIVKEY`` was fixed.
* Only new or changed ``.apk`` files (as determined by their timestamp)
  are re-signed, instead of re-signing all files in ``REPODEST``.
* Temporary keys are no longer copied to ``REPODEST`` if re-signing will
  occur.
* ``af-depgraph all-deps`` no longer wastes long periods of time tracing
  dependencies it has already seen.

0.5 - 2020-06-20
----------------

First "beta" release.
