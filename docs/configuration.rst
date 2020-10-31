*******************************
APK Foundry configuration files
*******************************

INI file format
---------------

Several configuration files for APK Foundry use a restricted subset of
the INI configuration file format. In particular:

* There is no interpolation of values.
* Values are separated from key names with an equals (``=``).
* Values can span multiple lines, as long as the continuation of the
  value is indented more than the key name. This includes empty lines.
* Comments are delimited with a semicolon (``;``).
* Comments cannot be on the same line as a value.

Site configuration
------------------

INI files
^^^^^^^^^

The main configuration files are stored in ``$AF_CONFIG/*.ini``. The
files can be named whatever one chooses; any files matching this glob
will be read in collation order. Thus sensitive details can be split
into restricted files away from more mundane options.

See `<docs/examples/config-site.ini>`_ for an annotated example
configuration file.

abuild.conf
^^^^^^^^^^^

In order to accommodate settings from both the builder operator and the
individual projects, the handling of the ``/etc/abuild.conf`` file
should be done with care. The builder operator should install a template
at ``$AF_CONFIG/abuild/abuild.conf`` to specify things like the
``$JOBS`` variable and possibly a packaging key. The contents of
``$AF_CONFIG/abuild`` will be installed to ``$ABUILD_USERDIR`` in the
container automatically during bootstrapping. If this ``abuild.conf``
specifies a ``$PACKAGER_PRIVKEY``, it should be relative to
``$ABUILD_USERDIR``, exist in the same directory, and have its
corresponding public key accessible at ``$PACKAGER_PRIVKEY.pub``.

If ``$PACKAGER_PRIVKEY`` is not specified here then it is up to the
project's bootstrap scripts to generate and install a key. The
``$ABUILD_USERDIR`` directory is guaranteed to exist before stage 2 of
bootstrapping, but not necessarily an ``abuild.conf`` within it.

Projects should copy their own abuild settings to ``etc/abuild.conf`` in
their refresh script.

Project configuration
---------------------

Each project's git repository should have an ``apkfoundry`` branch which
contains APK Foundry's configuration files. It consists of INI files at
the top level, and a directory for each branch. This branch is checked
out as a git worktree as ``.apkfoundry`` in the git repository's root.

INI files
^^^^^^^^^

The INI files are loaded according to the ``.apkfoundry/*.ini`` glob in
collation order, similar to the site configuration. The sections in
these INI files are named for the branches to which they apply. The
settings in the ``master`` section are used as a fallback for missing
settings.

See `<docs/examples/config-project.ini>`_ for an annotated example
configuration file.

Scripts
^^^^^^^

There are three scripts that are run during the lifetime of a job: the
bootstrap script, the refresh script, and the build script. While they
are referred to as "scripts" here and the examples are written in POSIX
shell, they can be any executable file that the container will be able
to run. The scripts (and any supporting files) should be placed in a
subdirectory of the ``.apkfoundry`` configuration directory. The name of
this subdirectory should correspond to the name of the branch to which
they apply. This subdirectory is known as the "branch directory". If a
branch directory doesn't exist for the branch the job is occurring on,
APK Foundry will fall back to using the ``master`` branch directory.

``bootstrap``
  This script is only run once: after the initial extraction of the root
  filesystem tarball. It should upgrade the packages the container if
  necessary, setup the unprivileged ``build`` user, and run any other
  one-time actions before the builds begin. It is run as the container's
  ``root`` user.

  See `<docs/examples/bootstrap.sh>`_ for an example written in POSIX
  shell.

``refresh``
  This script is run each time the container is opened. It should reset
  the container's ``/etc/apk/repositories`` and ``/etc/apk/world`` files
  to a known good state, typically depending on the APK repository that
  is about to be built. It is run as the container's ``root`` user.

  See `<docs/examples/refresh.sh>`_ for an example written in POSIX
  shell.

``build``
  This script is run in order to build each package for the job. It
  should call ``abuild`` or a provided wrapper (see below) at some
  point. It is run as the container's ``build`` user which maps to the
  same ID as the user running APK Foundry.

  The current working directory is set to ``APORTSDIR``, and the
  ``STARTDIR`` to build is passed as the first (and only) argument.

  See `<docs/examples/build.sh>`_ for an example written in POSIX shell.

To use these scripts, it's important to note that the names and file
permissions are important - namely the files must have the executable
bit set. For example:

.. code-block:: sh

   cp docs/examples/bootstrap.sh ~/aports/.apkfoundry/master/bootstrap
   cp docs/examples/refresh.sh ~/aports/.apkfoundry/master/refresh
   cp docs/examples/build.sh ~/aports/.apkfoundry/master/build
   chmod +x ~/aports/.apkfoundry/master/bootstrap
   chmod +x ~/aports/.apkfoundry/master/refresh
   chmod +x ~/aports/.apkfoundry/master/build

Script environment
^^^^^^^^^^^^^^^^^^

Inside the container, the following environment variables will be set:

``SRCDEST``
  Remote APKBUILD ``source`` files cache directory.

``APORTSDIR``
  Project's git repository checkout directory.

``REPODEST``
  Location where built ``.apk`` files are placed.

``ABUILD_USERDIR``
  ``build`` user's ``abuild`` settings directory. This is where the
  (optionally, temporary) package signing private and public keys are
  stored.

``ABUILD_USERCONF``
  ``build`` user's ``abuild`` configuration. This file should contain
  builder-specific settings like ``JOBS``.

``AF_LIBEXEC``
  Location of APK Foundry's internal executable binary directory which
  is mounted read-only inside the container.

``AF_BUILD_UID``
  User ID number for the ``build`` user; same as the user ID of the user
  executing APK Foundry.

``AF_BUILD_GID``
  Group ID number for the ``build`` group; same as the primary group ID
  of the user executing APK Foundry.

``AF_BRANCH``
  The branch currently being built. This should be used instead of
  inspecting using ``git`` since the checkout may be in a detached HEAD
  state. For merge requests, this is the target branch's name.

``AF_REPO``
  The APK repository currently being built.

``AF_ARCH``
  The APK architecture currently being built.

Container structure
^^^^^^^^^^^^^^^^^^^

During normal non-interactive operation, only the following locations
are read/write for the ``build`` user:

* ``HOME``: unique for each package being built. Various ``TMP``
  environment variables are also set to this location.
* ``REPODEST``
* ``SRCDEST``
* ``/tmp`` and ``/var/tmp``: in the future, these may point to the same
  location that ``HOME`` does.
* ``/af/build``: where ``src`` and ``pkg`` are placed for each package
  build

All other locations are mounted read-only. The ``build`` user cannot
access the network unless the package currently being built has
``options=net`` enabled. See `the APKBUILD expectations guide
<docs/APKBUILD.rst>`_ for information on how to correctly set
``options=net``.

The ``root`` user has read/write access to all locations except
``AF_LIBEXEC``, and can access the network.

During interactive use via the ``af-chroot`` command, regardless of the
user, the following rules apply. These rules may be changed in a future
version.

* The same read/write and read-only rules as the non-interactive
  ``build`` user above apply unless overridden using ``af-chroot``
  options ``--ro-aports`` and/or ``--rw-root``.
* Network isolation is in effect. Pass ``--networking`` to override.

The host system's ``/etc/hosts`` and ``/etc/resolv.conf`` are bind
mounted read-only as ``/af/config/host/hosts`` and
``/af/config/host/resolv.conf``.  The project's bootstrap configuration
should symlink to these files.

Requesting elevated permissions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

When running the ``build`` script it is necessary to request elevated
permissions in order to install dependencies, add users and groups, or
download remote source files if network isolation is in effect.

During normal non-interactive operation, and for ``af-chroot`` if the
``--no-sudo`` option is **not** passed, the following environment
variables are set to allow privileged command execution using an
internal daemon.

``ABUILD_FETCH``
  Calls ``abuild-fetch`` to download files when network
  isolation is in effect.
``ADDGROUP``
  Calls ``addgroup``.
``ADDUSER``
  Calls ``adduser``.
``SUDO_APK``
  Calls ``apk``.
``APK_FETCH``
  Calls ``apk``.

These environment variables may consist of multiple words and as such
should not be quoted in shell scripts, and should be broken at word
boundaries if used directly with ``exec(3)`` analogues.

.. code-block:: sh

   # Wrong
   "$SUDO_APK" add pigz
   # Right
   $SUDO_APK add pigz

``apk`` invocations are not allowed to use ``--allow-untrusted`` or
``--keys-dir``.

The current mechanism does not pass the current working directory or
any environment variables to the executed commands. This may change in a
future version.

The standard input, standard output, and standard error streams of the
requesting process are connected directly to the executed command.

The commands are run as ``root`` with read-write ``/`` access and
network access.

Writing scripts
^^^^^^^^^^^^^^^

The ``af-functions`` file in ``AF_LIBEXEC`` is a POSIX shell file that
defines some convenience functions for project use.

``af_mkuser``
  Create the ``build`` user and group with the correct IDs. Useful for
  the ``bootstrap`` script.

``af_userconf``
  Set up the ``ABUILD_USERCONF`` file. Generate a ``PACKAGER_PRIVKEY``
  if necessary, and install its corresponding public key to
  ``/etc/apk/keys``. Useful for the ``bootstrap`` script.

``af_loginit [-at]``
  Redirect standard output and standard error to a log file named
  ``$REPODEST/$repo/$CARCH/logs/$pkgname-$pkgver-r$pkgrel.log``
  depending on the APKBUILD in the current working directory. A symlink
  named ``/af/build/log`` will also point to this log file. Useful for
  the ``build`` script.

  Options:

  ``-a``
    append to ``.log`` file instead of overwriting. Do not enable this
    if the project has ``persistent_repodest`` enabled!
  ``-t``
    tee to original standard output

``af_abuild_env STARTDIR``
  Sets up the environment for ``abuild`` to perform out-of-tree builds.
  This is useful when trying to resume a failed build or otherwise run a
  build interactively when ``APORTSDIR`` is read-only.

``af_abuild_unpriv [abuild options...] [abuild phases...]``
  A wrapper that completely drops APK Foundry privileges before
  executing ``abuild``.

``af_abuild [-cDfkKmPqsv]``
  A wrapper for abuild that performs privileged actions first, then
  executes the rest of the build using ``af_abuild_unpriv``. It is
  equivalent to ``abuild -r``.

  No phases may be given.

  Only a subset of abuild options are supported.

Working example
^^^^^^^^^^^^^^^

For a complete working example of a project's APK Foundry configuration,
see `<https://code.foxkit.us/sroracle/af-config>`_.
