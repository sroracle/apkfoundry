*******************************
APK Foundry configuration files
*******************************

INI file format
---------------

Several configuration files for APK Foundry use a restricted subset of the
INI configuration file format. In particular:

* There is no interpolation of values.
* Values are separated from key names with an equals (``=``).
* Values can span multiple lines, as long as the continuation of the
  value is indented more than the key name. This includes empty lines.
* Comments are delimited with a semicolon (``;``).
* Comments cannot be on the same line as a value.

Site configuration
------------------

The main configuration files are stored in ``/etc/apkfoundry/*.ini``.
The files can be named whatever one chooses; any files matching this
glob will be read in collation order. Thus sensitive details can be
split into restricted files away from more mundane options.

::

    [agent]
    ; Name of the builder agent.
    name = agent01
    ; Path to the directory under which to store chroots.
    chroots = /var/lib/apkfoundry/agent
    ; The MQTT username for the builder agent.
    username=agent01
    ; The MQTT password for the builder agent.
    password=password
    ; MQTT wildcard topic on which to listen for jobs.
    mask=jobs/#
    ; Number of disjoint jobs allowed to run concurrently.
    jobs=1

    [chroot]
    ; ID of the af-root user.
    rootid = 1001
    ; Base sub-id for containers.
    subid = 100000
    ; Path to apk.static executable used for bootstrapping.
    apk = /sbin/apk.static
    ; Path to non-setuid bwrap executable.
    bwrap = /usr/bin/bwrap.nosuid
    ; Path to shared distfiles location.
    distfiles = /var/cache/distfiles
    ; Path to af-rootd UNIX domain socket.
    socket = /var/lib/apkfoundry/root.sock

    [database]
    ; The filename for the SQLite3 APK Foundry database. This should be
    ; read-writable by orchestrator, and readable by www. The file need
    ; only be accessable on the orchestrator machine.
    filename=/srv/apkfoundry/database.sqlite3

    [dispatch]
    ; The MQTT username for the job dispatcher.
    username=dispatch
    ; The MQTT password for the job dispatcher.
    password=password
    ; The path under which the notification FIFO and event files are
    ; stored. This path should be mode 3730 af-dispatch:www.
    events=/var/lib/apkfoundry/events
    ; The path under which the git repositories of the various projects
    ; will be stored.
    projects=/var/lib/apkfoundry/projects
    ; List of IP addresses from which to accept requests.
    remotes=127.0.0.1

    [mqtt]
    ; The hostname of the MQTT broker.
    host=localhost
    ; The port number on which the MQTT broker listens.
    port=1883

    [web]
    ; Whether to use PATH_INFO to generate pretty URIs.
    pretty=false

    [https://example.com/sroracle/packages.git]
    ; Whether to trigger builds on push events or not.
    push=false
    ; A list of branches on which push events will trigger builds.
    push_branches=

    ; Whether to trigger builds on merge request events or not.
    mr=false
    ; A list of target branches on which merge request events will
    ; trigger builds.
    mr_branches=
    ; A list of users to allow merge request events. If empty, any user
    ; can trigger an event. Otherwise, only the users on the list can.
    mr_users=

    ; Whether to trigger builds on comments on merge requests or not.
    note=false
    ; A list of users to allow note events. If empty, any user can
    ; trigger an event. Otherwise, only the users on the list can.
    note_users=
    ; A keyword that must be present in the comment to trigger the
    ; build.
    note_keyword=!build

Project-local configuration
---------------------------

The git repository for each project should have an ``apkfoundry`` branch.
This branch contains additional project-specific configuration files.
The branch should be set up such that there is a subdirectory in the
tree for each working branch name, each containing the following files:

branch/arch
^^^^^^^^^^^

This **required** file is used by ``af-arch``, the purpose being to
define which architectures the special ``arch`` values ``"all"`` and
``"noarch"`` should correspond to.  It should be a plain text file
separated by line feeds (``\n``). Each line should contain a single
architecture. For example, if ``master/arch`` contains the following::

    ppc
    ppc64
    pmmx
    x86_64

Then events that modify APKBUILDs in the ``master`` branch will generate
jobs for the ``ppc``, ``ppc64``, ``pmmx``, and ``x86_64`` architectures
as appropriate. If an architecture is not listed in these files, then no
builds will occur for that architecture, even if changed APKBUILDs have
``arch="all"``, ``arch="noarch"``, or even specifically name that
architecture.

The file can also be suffixed by a repository name to specify
architectures for that repository, e.g. ``master/arch.system``. Such a
file will completely override the repository-independent configuration
file.

branch/ignore
^^^^^^^^^^^^^

This **optional** file is used by the builder agents. It should be a
plain text file separated by line feeds (``\n``). Each line should
contain a single startdir, the purpose being that APK Foundry will ignore
this package even if it was changed during an event. For example, if
``master/ignore`` contains the following::

    user/libreoffice
    user/rust

Then the ``user/libreoffice`` and ``user/rust`` packages will never be
automatically built for events occurring against the ``master`` branch.

The file can also be suffixed by the APK architecture name to ignore
packages only on that architecture, e.g. ``master/ignore.aarch64``. Such
a file will completely override the architecture-independent
configuration file.

branch/ignore-deps
^^^^^^^^^^^^^^^^^^

This **optional** file is used by the builder agents. It should be a
plain text file separated by line feeds (``\n``). Each line should
contain a pair of startdirs, the purpose being that APK Foundry will ignore
this dependency when calculating the build order. For example, if
``master/ignore.deps`` contains the following::

    system/python3 system/easy-kernel
    system/attr system/libtool

Then build order resolution for builds occurring on or against the
``master`` branch will ignore ``system/python3``'s dependency on
``system/easy-kernel`` as well as ``system/attr``'s dependency on
``system/libtool``.

The file can also be suffixed by the APK architecture name to ignore
dependencies only on that architecture, e.g.
``master/ignore-deps.aarch64``. Such a file will completely override the
architecture-independent configuration file.

**Note:** ``abuild`` will still install such dependencies. This file
only affects APK Foundry's build order solver, the primary utility being to
break dependency cycles.

..

    branch/abuild.arch.conf
    ^^^^^^^^^^^^^^^^^^^^^^^

    These **required** file are used by the builder agents. They should be
    of the same format as a typical ``abuild.conf`` (i.e. a POSIX shell
    script). These files have a lower precedence than the builder-global
    ``abuild.conf`` files. In particular, these files should only set
    ``CFLAGS``, ``LDFLAGS``, ``CXXFLAGS``, ``CPPFLAGS``, and
    ``DEFAULT_DBG``. Other options will be overridden by the builder-global
    configuration.

branch/keys
^^^^^^^^^^^

This **required** directory is used by the builder agents. It should
contain keys that will ultimately be populated in ``/etc/apk/keys``.

branch/repositories
^^^^^^^^^^^^^^^^^^^

This **required** file is used by the builder agents. It should be of
the same format as a typical ``/etc/apk/repositories`` file.

The file can also be suffixed by a repository name to change the
available repositories only when building that repository, e.g.
``master/repositories.user``. Such a file will completely override the
repository-independent configuration file.

The file should only contain remote URIs, or the local package
repositories under ``/packages``::

    /packages/system
    /packages/user
    https://distfiles.adelielinux.org/adelie/current/system
    https://distfiles.adelielinux.org/adelie/current/user

Using only local repositories is especially advantageous when building a
new release of a distribution.

Tagged repositories should not be used since they will never be selected
by ``abuild`` or ``apk``.

branch/world
^^^^^^^^^^^^

This **required** file is used by the builder agents. It should be of
the same format as a typical ``/etc/apk/world`` file.
