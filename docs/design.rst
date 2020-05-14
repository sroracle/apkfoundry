*************************
APK Foundry design primer
*************************

APK Foundry is essentially a thick wrapper around the `bubblewrap
<https://github.com/containers/bubblewrap>`_ container tool. The desired
properties are the following:

* Isolation from the host system in order to yield a reproducible build
  environment.
* Use of the least privileges possible.
* Integration into existing CI infrastructures.
* As a matter of policy, network and key isolation by default.

Privilege handling
------------------

The primary needs for privilege inside the container is to use ``apk``
to install dependencies and to add users and groups needed by the build.
The traditional ``abuild`` workflow uses a setuid binary
(``abuild-apk``, ``abuild-adduser``, and ``abuild-addgroup`` which are
symlinked to ``abuild-sudo``) to accomplish this for users in the
``abuild`` group. Since ``bwrap`` sets the ``PR_SET_NO_NEW_PRIVS``
``prctl(2)`` option, setuid binaries do not work inside the container.
Instead, the ``af-root`` user (distinct from the build user) is
designated to map to UID zero inside the container and listens on a UNIX
domain socket for privileged commands to execute. This includes not only
the functionality of ``abuild-apk``, ``abuild-adduser``, and
``abuild-addgroup``, but also ``abuild-fetch`` and ``apk fetch`` (needed
when network isolation is in effect). The ``af-rootd`` daemon is
responsible for handling these requests and validating their
authorization. The ``af-req-root`` client is executed by the build user
to initiate these requests inside the container. By default, the
container environment is setup with ``SUDO_APK``, ``ADDUSER``,
``ADDGROUP``, ``ABUILD_FETCH``, and ``APK_FETCH`` to use
``af-req-root``.

In this model, the elevated privileges needed are:

* Launch ``af-rootd`` as the ``af-root`` user, distinct
  from the build user.
* Execute ``clone(2)`` with the ``CLONE_NEWUSER`` flag (this is an
  unprivileged action in the mainline kernel, but some distributions
  require the non-standard ``kernel.unprivileged_userns_clone`` sysctl
  to be enabled)
* Use the ``newuidmap`` and ``newgidmap`` setuid binaries (as provided
  by ``shadow-uidmap`` package) in order to setup a full mapping of user
  and group IDs inside the namespace, i.e. mapping the build user's
  IDs to themselves, the ``af-root`` user's IDs to zero, and all other
  IDs in the range [1, 65534] to unused IDs.

The job lifecycle
-----------------

Part of the `configuration<configuration.rst>`_ involves "skeletons" of
files. Each entry into the container refreshes the container's contents
from these skeletons. There is also a special "bootstrap skeleton" that
is used only when first building the container. This means that
container is typically reset to a reproducible state during each build.

#. Receive a list of packages to build, or determine what to build based
   on a git revision range

#. Generate a dependency graph in order to perform a topological sort of
   the packages to-be-built with respect to their dependencies

#. Bootstrap the container, if it does not already exist

   #. Stage 1 (outside container): download and unpack rootfs, add build
      user
   #. Run the ``refresh`` script inside the container
   #. Stage 2 (inside container): upgrade it, and generate and install a
      packaging key

#. Perform each build

   #. Run the ``refresh`` script inside the container
   #. Run the ``build-script`` inside the container

#. Re-sign ``.apk`` files outside of the container, if a re-signing key
   is given
#. Destroy the container
