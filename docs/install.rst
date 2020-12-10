**********************
Installing APK Foundry
**********************

#. Ensure all dependencies mentioned in the `README <README.rst>`_ are
   present.
#. Create ``config.mk``. Options:

   ``PREFIX``
     Defaults to ``usr``; can also be ``usr/local``. This is relative to
     ``$DESTDIR``, see below.

   ``DOCDIR``
     The location under which to install the files in ``docs/``. The
     default is ``$PREFIX/share/doc/apkfoundry``.

   ``LIBEXECDIR``
     The location where APK Foundry internal binaries should be placed.
     The default is ``$PREFIX/libexec/apkfoundry``. This will be baked
     into APK Foundry at ``make install`` time.

   ``BWRAP``
     Path to the non-setuid ``bwrap(1)`` binary. It can be an absolute
     path or a command name that is resolved using ``$PATH``. The
     default is ``bwrap.nosuid``.

   ``DEFAULT_ARCH``
     Default ``apk`` architecture name to use if none is given when
     bootstrapping containers. **The default is** ``x86_64`` **so you'll
     probably need to change this.**

   ``PYTHON``
     Path to the Python interpreter. Defaults to ``python3``.

   ``DESTDIR``
     Root directory under which to install. Defaults to ``$PWD/target``.

#. Run ``make configure``. This will bake in some of the options you
   specified in the previous step.
#. Run ``make``. This will build the Python files and the libexec static
   binaries.
#. Optionally, run ``make check``.
#. Run ``make install``.
