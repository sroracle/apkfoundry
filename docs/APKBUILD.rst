**********************************
APK Foundry: APKBUILD expectations
**********************************

Maintainer
----------

The ``Maintainer`` line should start in column one, like so::

    # Maintainer: Alyssa P. Hacker <alyssa@example.net>

There should only ever be one ``Maintainer``. It is also acceptable to
specify a team::

    # Maintainer: Adélie Perl Team <adelie-perl@lists.adelielinux.org>

If there is no maintainer, the ``Maintainer`` line should still be
included::

    # Maintainer: 

By convention, but not necessarily as a requirement of APK Foundry, a single
space is often placed after the colon.

**Rationale**. The ``Maintainer`` line is used to describe a package
task, being especially useful to filter searches in the web interface.
In the future, it can also be used to send emails when a task runs or
fails, etc. Since it is implemented as a comment, there is no need to
worry about expansions or conditions.

arch
----

The ``arch`` line should start in column one and be contained wholly in
a single line, with no conditional parameters or the like precluding its
assignment, like so::

    arch="all !x86_64 pmmx"

The values ``all`` and ``noarch`` both correspond to the contents of the
file ``.apkfoundry/$branch/$repo.arch`` in the project root, falling
back on ``.apkfoundry/master/$repo.arch`` if that does not exist, and
otherwise producing a fatal error in the orchestrator.

**Rationale**. The ``arch`` line is needed by the orchestrator in order
to determine on which architectures the given package must be built. It
is desirable that the orchestrator need not execute a shell in order to
parse the APKBUILD to retrieve only the value of ``arch`` so that a
chroot is not needed. Since this line almost never contains expansion or
is part of a conditional statement, this expectation should not present
any problems.

options
-------

If networking access is required by the package other than for the
purposes of fetching ``source``\s and installing dependencies, the
``options`` line should start in column one like so::

    options="net"

Other ``options`` may follow the value of ``net``, but ``net`` should
always be first::

    options="net !check suid"

If part of the ``options`` depends on a condition and the package
requires networking access like above, ``options`` should still be
assigned statically first and then conditionally assigned later::

    options="net"
    [ "$CARCH" = "armhf" ] && options="$options !check"

**Rationale**. The ``options`` line is needed by the builder agent in
order to determine whether the package requires networking access for
its build or not. Since this needs to be determined before entering the
chroot (since networking access is dropped or kept at the chroot
boundary), it is desirable to parse this requirement statically without
the use of a shell.
