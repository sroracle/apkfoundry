****************************
APK Foundry: getting started
****************************

#. Ensure all dependencies mentioned in the `README <README.rst>`_ are
   present.
#. Run ``make quickstart``. This will configure APK Foundry and build
   the two static binaries that are needed inside the container. It
   accepts these configuration options:

   ``BWRAP``
     Path to the non-setuid ``bwrap(1)`` binary. It can be an absolute
     path or a command name that is resolved using ``$PATH``. The
     default is ``bwrap.nosuid``.

   ``DEFAULT_ARCH``
     Default ``apk`` architecture name to use if none is given when
     bootstrapping containers. The default value is the output of
     ``apk --print-arch`` which may not be available on all systems.

   For example:

   .. code-block:: shell

     make quickstart BWRAP=/path/to/bwrap.nosuid DEFAULT_ARCH=ppc64

   These options are baked into APK Foundry.

#. Add mappings to ``/etc/subuid`` and ``/etc/subgid`` for this user.
   See ``subuid(5)`` and ``subgid(5)``. You will need 65536 UIDs and
   GIDs, and they must start at the same base sub-ID (this may be
   changed in a future version). For example:

   .. code-block::

     build:100000:65536

#. Create a site configuration file in ``$AF_CONFIG`` with a name like
   ``config.ini``. ``$AF_CONFIG`` defaults to
   ``$XDG_CONFIG_HOME/apkfoundry`` if not set. ``$XDG_CONFIG_HOME``
   defaults to ``$HOME/.config`` if not set.

   Here you record what the base sub-ID is from the previous step:

   .. code-block:: ini

     [container]
     subid = 100000

   If your machine is 64-bit and can support 32-bit environments as
   well, you should also configure here what arguments with which
   ``setarch(8)`` needs to be called to support that. For example, if
   the machine is a 64-bit x86 machine and can support 32-bit x86
   environments:

   .. code-block:: ini

     [setarch]
     pmmx = i586

   This will configure APK Foundry to start all containers for the
   ``pmmx`` APK architecture with ``setarch i586``.

   For more information on site setings, see `the annotated example site
   configuration file <docs/config-site.ini>`_.

#. Optionally, create ``$AF_CONFIG/abuild/abuild.conf`` so that you can
   set ``$JOBS``. For example:

   .. code-block:: sh

     export JOBS=2
     export MAKEFLAGS=-j$JOBS

   This will be installed along with the rest of ``$AF_CONFIG/abuild``
   into each container's ``$ABUILD_USERDIR``. See `the configuration
   guide <docs/configuration.rst>`_ for more information.

#. Configure your project to support APK Foundry. See `the configution
   guide <docs/configuration.rst>`_ for details.
#. Add ``/path/to/apkfoundry`` to your ``$PYTHONPATH``.
#. Add ``/path/to/apkfoundry/bin`` to your ``$PATH``.
#. Explore!
