***********************************
APK Foundry commit message commands
***********************************

Skipping automatic builds
-------------------------

In order to temporarily skip an automatic build for a package, APK
Foundry scans incoming commit messages for two keywords, both case
insensitive.

This feature is only enabled if the ``branch/arch-pkg`` `project-local
configuration file <configuration.rst>`_ exists for the given branch (it
can be completely blank).

``AF-Arch:``
    If this tag is located at the beginning of a line in the commit
    message, then it specifies a temporary restriction on the ``$arch``
    of the APKBUILD(s) to which it applies. The rules are the same as
    those of the ``branch/arch-pkg`` file in the project-local
    configuration: it can only restrict the automatic build architecture
    list for this package, not expand it. Additionally, it has a lower
    precedence than the ``branch/arch-pkg`` file, i.e. if an
    architecture is disabled in that file for this package, then this
    tag cannot override it.

``[ci skip]``
    This keyword can be located anywhere in the commit message or
    subject. It is equivalent to a blank ``AF-Arch:`` tag (i.e., do not
    automatically build on any architecture).

For each APKBUILD, the commits that modify that APKBUILD in a push or a
merge request must all have the same ``AF-Arch`` tag in order to be
skipped. **If not all of the ``AF-Arch`` tags match (including ``[ci
skip]`` acting as a blank tag), then they are all ignored.**

For example, say that a user pushes a single commit to the ``master``
branch to modify the ``user/libreoffice`` package. The APKBUILD contains
the following::

    arch="all"

The ``master/arch`` project-local configuration contains the following::

    user pmmx x86_64 ppc ppc64 aarch64

The ``master/arch-pkg`` project-local configuration contains the
following::

    user/libreoffice all !ppc64

Finally, the commit contains the following line::

    AF-Arch: ppc64 ppc

Then an automatic build will only be triggered for the ``ppc``
architecture. Again, relaxations are not allowed. If the commit
contained this line instead::

    AF-Arch: armv7

Since the ``master/arch`` file does not include ``armv7``, this tag
would be equivalent to a blank tag::

    AF-Arch:

Which would mean that no builds are triggered. Blacklisting is also
possible::

    AF-Arch: all !aarch64 !armv7

This would build on all architectures except ``ppc64`` (from
``arch-pkg``) and ``aarch64`` (from the commit message). Again,
``armv7`` isn't enabled for ``user/`` anyway, so that part is ignored.
In this context, ``all`` and ``noarch`` can be used interchangeably and
both map to the contents of the ``branch/arch`` project-local
configuration.
