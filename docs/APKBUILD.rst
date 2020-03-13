**********************************
APK Foundry: APKBUILD expectations
**********************************

options
-------

If networking access is required by the package other than for the
purposes of fetching ``source``\s and installing dependencies, the
``options`` line should start in column one like so:

.. code-block:: shell

    options="net"

This can be mixed with other options:

.. code-block:: shell

    options="!check net suid"

If part of the ``options`` depends on a condition and the package
requires networking access like above, ``options`` should still be
assigned statically first and then conditionally assigned later:

.. code-block:: shell

    options="net"
    [ "$CARCH" = "armhf" ] && options="$options !check"

**Rationale**. The ``options`` line is needed by the builder agent in
order to determine whether the package requires networking access for
its build or not. Since this needs to be determined before entering the
container (since networking access is dropped or kept at the container
boundary), it is desirable to parse this requirement statically without
the use of a shell.
