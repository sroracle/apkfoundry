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

The main configuration files are stored in ``/etc/apkfoundry/*.ini``.
The files can be named whatever one chooses; any files matching this
glob will be read in collation order. Thus sensitive details can be
split into restricted files away from more mundane options.

::

    [container]
    ; Base sub-id for containers.
    subid = 100000
    
    [setarch]
    ; For each architecture flavor, list here what needs to be passed to
    ; setarch(8) (if anything).
    ;
    ; For example, on an x86_64 machine you would typically build x86_64
    ; packages (duh). For any architecture flavor that needs no call to
    ; setarch(8), no configuration is needed here.
    ;
    ; However, you may also want to build packages for a 32-bit variant such
    ; as Pentium MMX. For that, we need to call setarch(8) with "i586" as an
    ; argument. To configure this, you would write:
    pmmx = i586

Site bootstrap skeleton
^^^^^^^^^^^^^^^^^^^^^^^

The site bootstrap skeleton, located in
``/etc/apkfoundry/skel.boostrap``, contains files that are temporarily
copied into the container when it is first being created. Once the
container bootstrapping process is over, these files will be removed if
they are not claimed by any package.

Required contents are:

``apk.static``
    This is the statically linked ``apk(8)`` binary that is used to
    bootstrap the installation of the packages inside of the container.

Recommended contents for HTTPS support are:

``etc/apk/ca.pem``
    This is a certificate authority file which can contain multiple
    certificate authority certificates. It should probably be symlinked
    to ``/etc/ssl/certs/ca-certificates.crt`` or similar.

``etc/services``
    This is the Internet network services list ``services(5)`` file,
    which is needed to determine the port on which HTTPS connections
    occur. It should probably be symlinked to ``/etc/services``.

Site skeleton
^^^^^^^^^^^^^

These files, located in ``/etc/apkfoundry/skel``, are copied into the
container for each session, including during the bootstrapping process.
Any existing files in the container will be overwritten.

Recommended contents are:

``etc/hosts``
    The ``hosts(5)`` static hostname lookup file. Usually symlink to
    ``/etc/hosts``.

``etc/resolv.conf``
    The ``resolv.conf(5)`` DNS resolution configuration file. Usually
    symlink to ``/etc/resolv.conf``.

``etc/passwd``
    The ``passwd(5)`` user login database file.

``etc/group``
    The ``group(5)`` user group database file.

abuild.conf
^^^^^^^^^^^

In order to accommodate settings from both the builder operator and the
individual projects, handling of the ``/etc/abuild.conf`` file is
separate from the skeletons. The site configuration is located in
``/etc/apkfoundry/abuild.conf``, with the following recommended minimum
requirements::

    # Include project-local abuild settings
    if [ -e /etc/abuild.conf.local ]; then
        . /etc/abuild.conf.local
    fi

Typically, after including the project-local settings, the site-local
configuration will set things such as ``$JOBS``::

    export JOBS=4
    export MAKEFLAGS="$MAKEFLAGS -j$JOBS"

Project-local configuration
---------------------------

For each branch to be built, it should have an ``.apkfoundry`` directory
in its repository root.

branch/repos
^^^^^^^^^^^^

The purpose of this **required** is to define which architectures the
special ``arch`` values ``"all"`` and ``"noarch"`` should correspond to
for each APK repository. It should be a plain text file separated by
line feeds (``\n``). Each line should contain a single repository name,
followed by the architectures that the repository supports. For example,
if the file contained the following::

    system ppc ppc64 pmmx x86_64
    user ppc64 x86_64

Then, for APKBUILDs on this branch:

* If the APKBUILD is in the ``system`` repository, then jobs will be
  executed for the ``ppc``, ``ppc64``, ``pmmx``, and ``x86_64``
  architectures.
* If the APKBUILD is in the ``user`` repository, then jobs will be
  executed for the ``ppc64`` and ``x86_64`` architectures.
* Any other architectures will have their jobs skip these APKBUILDs.
* The ordering of lines in the file is not significant. The dependency
  resolution engine always considers APKBUILDs from every available
  repository. In order to prevent one repository from depending on
  another, change the ``repositories`` file in its skeleton as
  appropriate.

If an architecture is not listed in this file, then no builds will occur
for that architecture, even if changed APKBUILDs have ``arch="all"``,
``arch="noarch"``, or even specifically name that architecture.

If a repository is not listed in this file, then no builds will occur
for that repository.

branch/ignore-deps
^^^^^^^^^^^^^^^^^^

This **optional** file is used by the runners to ignore cyclic
dependencies when calculating the build order. It should be a plain text
file separated by line feeds (``\n``). Each line should contain a pair
of startdirs.  For example, if it contains the following::

    system/python3 system/easy-kernel
    system/attr system/libtool

Then the build order calculation will ignore ``system/python3``'s
dependency on ``system/easy-kernel`` as well as ``system/attr``'s
dependency on ``system/libtool``.

**Note:** ``abuild`` will still install such dependencies. This file
only affects APK Foundry's build order solver, the primary utility being
to break dependency cycles. If you wish to prevent a package from ever
being installed, add ``!pkgname`` to your world file.

Additionally, if a package has a build-time dependency (``makedepends``)
on its own subpackage, you will need to install that yourself before the
build since ``abuild`` skips such dependencies. A future version of APK
Foundry may provide a configuration file for this purpose.

Skeletons
^^^^^^^^^

Similar to the site configuration skeleton directory, projects have
their own skeletons that are forcibly copied into the container during
each session. Each skeleton can be general, for a specific repository,
for a specific architecture, or for a specific repository / architecture
combination. The order in which the skeletons are copied into the
container is:

1. ``/etc/apkfoundry/skel``

   As discussed previously.

2. ``.apkfoundry/skel``

   General skeleton for this branch. Recommended contents:

   ``etc/apk/keys``
       The public keys in this directory will be used by ``apk(8)`` to
       verify packages.

   ``etc/apk/world``
       The file containing the names of packages that are to be
       explicitly installed.

3. ``.apkfoundry/skel.repo``

   Skeleton for this branch and repository. Recommended contents:

   ``etc/apk/repositories``
       The file containing the URLs and local paths to the repositories
       from which to obtain packages.

4. ``.apkfoundry/skel..arch``

   Skeleton for this branch and architecture. Recommended contents:

   ``etc/abuild.conf.local``
       The configuration file for ``abuild(1)`` itself. Usually has
       architecture specific parameters such as ``CFLAGS``. It must end
       in with a ``.local`` extension, as ``etc/abuild.conf`` will be
       overridden by the site configuration as discussed previously.

5. ``.apkfoundry/skel.repo.arch``

   Skeleton for this branch, repository, and architecture.
