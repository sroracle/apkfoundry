# abuildd

an Alpine archive management software replacement


## synopsis

`abuildd` contains multiple components that replaces the entire Alpine archive management
software.  These are:

 * `abuildd-build`: runs a build and stages artifacts to a designated location

 * `abuildd-agentd`: runs as an agent and consumes MQTT messages for build requests

 * `abuildd-collect`: retrieves artifacts from a build server for a specific build

 * `abuildd-compose`: gathers all collected artifacts and composes a repository or
                      distribution

 * `abuildd-enqueue`: enqueues new packages for building with dependency resolution

 * `abuildd-git-hook`: runs `abuild-enqueue` as necessary when new git commits are
                       received

 * `abuildd-monitord`: a monitoring daemon which watches the MQTT server for feedback from
                       the build servers

 * `abuildd.webhook`: a webhook implementation which enqueues new packages based on
                      changeset notifications

 * `abuildd.status`: an `aiohttp.web` application which shows current status of the
                     build servers, also includes `abuildd.webhook`

`abuildd` depends on a preconfigured postgresql database and mqtt server, you can use any
mqtt server you wish for the task (mosquitto, rabbitmq, etc.).  It also depends on bubblewrap
being installed for sandboxing the build.


## PPAs

`abuildd` can be configured to build PPAs, as well as official repos.  See the `abuildd-git-hook`
documentation for more details.  Alternatively, a Github webhook can be found in the
`abuildd.webhook` module.  The webhook module requires gunicorn and aiohttp.

## Webhook

Still a work in progress - mostly finished but needs an installer. To set it up and play
with it, here's a quick and dirty rundown:

```
# mkdir /etc/abuildd
# cp conf/*.ini /etc/abuildd
# $EDITOR /etc/abuildd/*.ini
$ echo 'CREATE DATABASE abuildd;' | psql -U postgres
$ psql -U postgres -d abuildd -f abuildd/abuildd.sql
$ virtualenv /path/to/new/venv
$ source /path/to/new/venv/bin/activate
(venv) $ pip install hbmqtt aiohttp asyncpg pyirc
(venv) $ export PYTHONPATH="$(pwd):/path/to/py3-abuild:$PYTHONPATH"
```

Then create a bare git clone for each project you want to support. A project's name is
simply its git URL with slashes replaced by full stops, e.g.
`code.foxkit.us.sroracle.packages.git`.

```
(venv) $ git clone --bare https://git/clone/url.git git.clone.url.git
(venv) $ /path/to/webhook.py
```

The webhook can be added to a GitLab project by going to Settings > Web Hooks. Currently,
"Push Events", "Comments" (on merge requests; "notes" internally), and "Merge Request
Events" are supported.


