* (project, type, target) serialization to be done at dispatcher level,
  not builder level

  * if blocking is enabled, block project at dispatcher level until
    block is removed - new status type?

* Artifact synchronization at the dispatcher needs to be made race-free

  * authorized_keys command= similar to rrsync but which obtains a lock
    on the repo from the dispatcher
  * dispatcher then updates APKINDEX with its own key

* Interstitial logging

  * Attach logger, handler to object to log to a file in the artifact
    directory
  * Handler lifetime is tied to object lifetime, but this would cause a
    problem with number of file descriptors for the dispatcher queue if
    it becomes too lengthy
  * If the queues are shortened such that there is typically only ever
    one job per arch in the queue and the MQTT thread notifies the
    DB thread when it needs new jobs, then this can probably be avoided.
    It would also have a nice side effect of having a better grasp of
    what is waiting and what isn't, and make it easier to inject manual
    events.

* Agent parallelism needs to be fixed

  * Does not currently obtain lock for each container
  * Tie in with job rejection if lock is already held

* Arch support needs to be generalized to match setarch, then
  projects can declare any number of "arch flavors" (e.g. pmmx, x86,
  ...) based on "real" arches that builders support

* Cancellation

  * On builder side... since threads typically will not wait before they
    are started (since they will be rejected instead and returned to
    dispatcher), some sort of communication from agent to worker must be
    established (currently only the opposite exists)
  * This may be simpler to implement if multiprocessing is used instead
    of multithreading in this case, since it can then just be done via
    signals

* Container destruction

      "apk is capable of deleting itself"

      -- A. Wilcox

* af-req-root - needs to be suffixed by architecture...
* ``f"{event.type}"`` is ``str(int)`` - needs fixing in build, cgi
* global replace ``/`` in branch by ``:``
* ``webhook``: rate limiting
* ``webhook``: GitLab secret token
* ``irc``: restore
* Artifact arch dirs need to be automatically created
* Configure shared distfiles
