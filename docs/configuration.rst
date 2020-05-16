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

The main configuration files are stored in ``SYSCONFDIR/*.ini``. The
files can be named whatever one chooses; any files matching this glob
will be read in collation order. Thus sensitive details can be split
into restricted files away from more mundane options.

See `<etc/config-global.ini>`_ for an annotated example configuration
file.

abuild.conf
^^^^^^^^^^^

In order to accommodate settings from both the builder operator and the
individual projects, the handling of the ``/etc/abuild.conf`` file
should be done with care. The builder operator should install a template
at ``SYSCONFDIR/abuild.conf`` which specifies things like the
``$JOBS`` variable and includes projects' configurations from
``etc/abuild.conf.local`` inside the container. Projects should copy
``SYSCONFDIR/abuild.conf`` to ``etc/abuild.conf`` and their own abuild
settings to ``etc/abuild.conf.local`` during bootstrapping.

An example template can be found at `<etc/abuild.conf>`_.

Project-local configuration
---------------------------

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

See `<docs/config-project.ini>`_ for an annotated example configuration
file.
