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

    [agent]
    ; Name of the builder agent.
    name = agent01
    ; Path to the directory under which to store containers.
    containers = /var/lib/apkfoundry/containers
    ; Path to the directory under which to store job artifacts.
    artifacts = /var/lib/apkfoundry/artifacts
    ; rsync URI to which artifacts are pulled from and pushed to.
    remote_artifacts = user@localhost:/var/lib/apkfoundry/artifacts
    ; The MQTT username for the builder agent.
    username=agent01
    ; The MQTT password for the builder agent.
    password=password
    ; Architectures supported by this builder agent.
    arches = apk_arch1
             apk_arch2:setarch2
    ; MQTT wildcard topic on which to listen for jobs.
    mask=jobs/#
    ; Number of disjoint jobs allowed to run concurrently.
    concurrency=1

    [container]
    ; ID of the af-root user.
    rootid = 1001
    ; Base sub-id for containers.
    subid = 100000
    ; Path to af-rootd UNIX domain socket.
    socket = /var/lib/apkfoundry/root.sock

    [database]
    ; The filename for the SQLite3 APK Foundry database. This should be
    ; read-writable by orchestrator, and readable by www. The file need
    ; only be accessable on the orchestrator machine.
    filename=/var/lib/apkfoundry/database.sqlite3

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
    ; Path to the directory under which to store job artifacts.
    artifacts = /var/lib/apkfoundry/artifacts
    ; List of IP addresses from which to accept requests.
    remotes=127.0.0.1
    ; Whether to remove event files after they are processed. This
    ; should generally be disabled except for debugging.
    keep_events=false

    [mqtt]
    ; The hostname of the MQTT broker.
    host=localhost
    ; The port number on which the MQTT broker listens.
    port=1883

    [web]
    ; URL for the web interface index.
    base=https://example.com/cgi-bin/apkfoundry-index.py
    ; URL for style.css.
    css=/style.css
    ; URL for the artifacts directory
    artifacts=/artifacts
    ; Whether to use PATH_INFO to generate pretty URIs.
    pretty=false
    ; Default maximum number of rows to return on each page.
    limit=50
    ; Whether to show debugging information (CGI tracebacks, SQL queries,
    ; etc).
    debug=false

    [https://example.com/user/packages.git]
    ; Project name.
    name=user:packages

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

    ; GitLab integration.
    ; If the following two options are specified, the dispatcher will
    ; attempt to post the status of each job update to its relevant
    ; commit. This will show as a "pending", "running", "succeeded", or
    ; "failed" symbol on each newest commit in a push to a branch, or on
    ; any related merge request.
    ;
    ; Authentication is done via GitLab's "Personal Access Token"
    ; feature. Follow the instructions from GitLab's documentation, and
    ; paste the resulting token here. NOTE: the user to which the token
    ; belongs must have sufficient privilege in order to post job statuses
    ; to commits.
    ; https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html
    ;
    ; If no token is specified, this feature will be disabled.
    gitlab_token=

    ; GitLab API endpoint for this project.
    ; Specify as https://gitlab.example.com/api/v4/projects/<your project ID>,
    ; where the ID can be a number (from the project settings page) or a
    ; url-encoded project path (e.g. group%2Fproject for group/project)
    ;
    ; If no endpoint is specified, this feature will be disabled.
    gitlab_endpoint=

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

The git repository for each project should have an ``apkfoundry`` branch
which will be checked out as a worktree in the ``.apkfoundry`` directory
in the repository root. This branch contains additional project-specific
configuration files. The branch should be set up such that there is a
subdirectory in the tree for each working branch name, each containing
the following files. In the ``.apkfoundry`` directory itself there can
be any number of ``.ini`` files in the same format as discussed
previously; they will be read in collation order. The contents of the
INI files can look something like the following.

::

    [DEFAULT]
    ; Global project settings are entered in the [DEFAULT] section.

    ; Action to take when the builder agent encounters a build ERROR or
    ; FAIL. Possible actions:
    ;
    ; * stop (default): immediately end the job.
    ; * recalculate: recalculate the build order by removing any tasks
    ;   that direclty or indirectly depend on this task, then continuing.
    ; * ignore: just continue with the job.
    ;
    on_failure = stop

    ; Settings can also be scoped by event type (overrides global
    ; project settings).
    ; [MR]
    ; on_failure = ignore
    ;
    ; [PUSH]
    ; on_failure = recalculate
    ;
    ; Or by a combination of event type and target branch (overrides
    ; both).
    ;
    ; [MR:master]
    ; on_failure = recalculate
    ;
    ; [PUSH:master]
    ; on_failure = stop

branch/arch
^^^^^^^^^^^

This **required** file is used by ``af-arch``, the purpose being to
define which architectures the special ``arch`` values ``"all"`` and
``"noarch"`` should correspond to.  It should be a plain text file
separated by line feeds (``\n``). Each line should contain a single
repository name, followed by the architectures that the repository
supports. For example, if ``master/arch`` contains the following::

    system ppc ppc64 pmmx x86_64
    user ppc64 x86_64

Then, for events that modify APKBUILDs in the ``master`` branch:

* If the APKBUILD is in the ``system`` repository, then jobs will be
  generated for the ``ppc``, ``ppc64``, ``pmmx``, and ``x86_64``
  architectures.
* If the APKBUILD is in the ``user`` repository, then jobs will be
  generated for the ``ppc64`` and ``x86_64`` architectures.
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

branch/arch-pkg
^^^^^^^^^^^^^^^

This **optional** file is used by ``af-arch``, the purpose being to
further restrict the ``$arch`` property of each APKBUILD in the context
of automatic builds. It should consist of a plain text file separated by
line feeds (``\n``). Each line should contain a single startdir,
followed by the architecture restrictions for that startdir. For
example, if ``master/arch-pkg`` contains the following::

    system/gcc all !aarch64 !armv7
    user/libreoffice

Then, for events that modify any of the above startdirs' APKBUILDs in
the ``master`` branch:

* For ``system/gcc``, builds will be triggered for ``all``
  (corresponding to ``system`` in ``master/arch``) except for
  ``aarch64`` and ``armv7``.
* For ``user/libreoffice``, no builds will be triggered (empty list).
* For any packages not specified in this file, builds will be triggered
  according to the intersection of their ``$arch`` and the architectures
  enabled for their repository (as specified by the ``branch/arch``
  file).

This file is only to restrict the architectures on which an automatic
build can be run, not to expand it. Therefore if an architecture listed
in this file is not in the APKBUILD's ``$arch`` property, or if the
architecture is not enabled for that repository (``branch/arch`` file),
a build will still not be triggered for that architecture, even if it is
explicitly listed in this file.

`A similar functionality can be accessed from commit messages.
<commits.rst>`_

branch/ignore
^^^^^^^^^^^^^

This **optional** file is used by the builder agents. It should be a
plain text file separated by line feeds (``\n``). Each line should
contain a single startdir, the purpose being that APK Foundry will
ignore this package even if it was changed during an event. For example,
if ``master/ignore`` contains the following::

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
contain a pair of startdirs, the purpose being that APK Foundry will
ignore this dependency when calculating the build order. For example, if
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
only affects APK Foundry's build order solver, the primary utility being
to break dependency cycles. If you wish to prevent a package from ever
being installed, add ``!pkgname`` to your world file.

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

2. ``.apkfoundry/branch/skel``

   General skeleton for this branch. Recommended contents:

   ``etc/apk/keys``
       The public keys in this directory will be used by ``apk(8)`` to
       verify packages.

   ``etc/apk/world``
       The file containing the names of packages that are to be
       explicitly installed.

3. ``.apkfoundry/branch/skel.repo``

   Skeleton for this branch and repository. Recommended contents:

   ``etc/apk/repositories``
       The file containing the URLs and local paths to the repositories
       from which to obtain packages.

4. ``.apkfoundry/branch/skel..arch``

   Skeleton for this branch and architecture. Recommended contents:

   ``etc/abuild.conf.local``
       The configuration file for ``abuild(1)`` itself. Usually has
       architecture specific parameters such as ``CFLAGS``. It must end
       in with a ``.local`` extension, as ``etc/abuild.conf`` will be
       overridden by the site configuration as discussed previously.

5. ``.apkfoundry/branch/skel.repo.arch``

   Skeleton for this branch, repository, and architecture.
