Next release:

* bug? supplementary groups which aren't mapped inside the container
  aren't dropped

  * This causes the coreutils and rsync check()s to fail because they
    then think that 65534 is a valid GID to try to chgrp things to
  * need to investigate the properties of these unmapped groups and
    whether they can just be dropped safely

* bug: af-depgraph: don't apply deps_ignore unless producing a tsort
* bug: af-deps: don't ignore cmd: anymore; we can use deps_map for that
* docs: add documentation about the internal environment and scripting
* feature: af-buildrepo: add --interactive

Future releases:

* feature: resignapk should only re-sign new .apks
* feature: project configuration - uploading
* feature: reusing containers - detect if CDIR passed to buildrepo is
  already bootstrapped
* feature: af-buildrepo cloning with external .apkfoundry
* feature: Restore webhook server for running pipelines against other
  repos?
* bug: gl-run should use ``SYSTEM_FAILURE_EXIT_CODE`` and
  ``BUILD_FAILURE_EXIT_CODE``
