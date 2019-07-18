PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS events (
  id          INTEGER PRIMARY KEY,
  project     TEXT    NOT NULL,
  type        INT     NOT NULL,
  clone       TEXT    NOT NULL,
  target      TEXT    NOT NULL,
  mrid        INT,
  mrclone     TEXT,
  mrbranch    TEXT,
  revision    TEXT    NOT NULL,
  user        TEXT    NOT NULL,
  reason      TEXT    NOT NULL,
  status      INT     NOT NULL
    DEFAULT 1,
  created     TIMESTAMP NOT NULL
    DEFAULT CURRENT_TIMESTAMP,
  updated     TIMESTAMP NOT NULL
    DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER IF NOT EXISTS events_timestamp
  AFTER UPDATE ON events
FOR EACH ROW BEGIN
  UPDATE events SET updated = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TABLE IF NOT EXISTS jobs (
  id          INTEGER PRIMARY KEY,
  event       INTEGER NOT NULL,
  builder     TEXT,
  arch        TEXT    NOT NULL,
  status      INT     NOT NULL
    DEFAULT 1,
  created     TIMESTAMP NOT NULL
    DEFAULT CURRENT_TIMESTAMP,
  updated     TIMESTAMP NOT NULL
    DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(event) REFERENCES events(id)
);

CREATE TRIGGER IF NOT EXISTS jobs_timestamp
  AFTER UPDATE ON jobs
FOR EACH ROW BEGIN
  UPDATE jobs SET updated = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS jobs_status
  AFTER UPDATE OF status ON jobs
FOR EACH ROW BEGIN
  UPDATE events SET status =
    CASE
    WHEN NOT EXISTS
      -- (1, 4) = (new, start)
      (SELECT 1 FROM jobs WHERE status IN (1, 4) AND event = NEW.event)
    THEN
        CASE
        WHEN 56 IN (SELECT DISTINCT status FROM jobs WHERE event = NEW.event)
        THEN 56 -- cancel
        WHEN 24 IN (SELECT DISTINCT status FROM jobs WHERE event = NEW.event)
        THEN 24 -- error
        WHEN 152 IN (SELECT DISTINCT status FROM jobs WHERE event = NEW.event)
        THEN 152 -- fail
        WHEN 312 IN (SELECT DISTINCT status FROM jobs WHERE event = NEW.event)
        THEN 312 -- depfail
        ELSE 72 -- success
        END
    -- if the event is currently new then start it
    WHEN status = 1 AND NEW.status != 1
    THEN 4
    -- otherwise no change
    ELSE status
    END
  WHERE id = NEW.event;
END;

CREATE TABLE IF NOT EXISTS tasks (
  id          INTEGER PRIMARY KEY,
  job         INTEGER NOT NULL,
  repo        TEXT    NOT NULL,
  pkg         TEXT    NOT NULL,
  maintainer  TEXT,
  status      INT     NOT NULL
    DEFAULT 1,
  tail        TEXT,
  created     TIMESTAMP NOT NULL
    DEFAULT CURRENT_TIMESTAMP,
  updated     TIMESTAMP NOT NULL
    DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(job) REFERENCES jobs(id)
);

CREATE TABLE IF NOT EXISTS artifacts (
  id          INTEGER PRIMARY KEY,
  task        INTEGER NOT NULL,
  name        TEXT NOT NULL,
  size        INTEGER NOT NULL,
  created     TIMESTAMP NOT NULL
    DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(task) REFERENCES tasks(id)
);

CREATE TRIGGER IF NOT EXISTS tasks_timestamp
  AFTER UPDATE ON tasks
FOR EACH ROW BEGIN
  UPDATE tasks SET updated = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;

CREATE TRIGGER IF NOT EXISTS tasks_status
  AFTER UPDATE OF status ON tasks
FOR EACH ROW BEGIN
  UPDATE jobs SET status =
    CASE
    WHEN NOT EXISTS
      -- (1, 4) = (new, start)
      (SELECT 1 FROM tasks WHERE status IN (1, 4) AND job = NEW.job)
    THEN
        CASE
        WHEN 56 IN (SELECT DISTINCT status FROM jobs WHERE job = NEW.job)
        THEN 56 -- cancel
        WHEN 24 IN (SELECT DISTINCT status FROM jobs WHERE job = NEW.job)
        THEN 24 -- error
        WHEN 152 IN (SELECT DISTINCT status FROM jobs WHERE job = NEW.job)
        THEN 152 -- fail
        WHEN 312 IN (SELECT DISTINCT status FROM jobs WHERE job = NEW.job)
        THEN 312 -- depfail
        ELSE 72 -- success
        END
    -- if the job is currently new then start it
    WHEN status = 1 AND NEW.status != 1
    THEN 4
    -- otherwise no change
    ELSE status
    END
  WHERE id = NEW.job;
END;

CREATE VIEW IF NOT EXISTS jobfull AS
SELECT
  jobs.id AS id,
  jobs.event AS event,
  jobs.builder AS builder,
  jobs.arch AS arch,
  jobs.status AS status,
  jobs.created AS created,
  jobs.updated AS updated,
  events.id AS e_id,
  events.project AS project,
  events.type AS type,
  events.clone AS clone,
  events.target AS target,
  events.mrid AS mrid,
  events.mrclone AS mrclone,
  events.mrbranch AS mrbranch,
  events.revision AS revision,
  events.user AS user,
  events.reason AS reason,
  events.created AS e_created,
  events.updated AS e_updated
FROM jobs
INNER JOIN events ON jobs.event = events.id;

CREATE VIEW IF NOT EXISTS taskfull AS
SELECT
  tasks.id AS id,
  tasks.job AS job,
  tasks.repo AS repo,
  tasks.pkg AS pkg,
  tasks.maintainer AS maintainer,
  tasks.status AS status,
  tasks.tail AS tail,
  tasks.created AS created,
  tasks.updated AS updated,
  jobfull.id AS j_id,
  jobfull.event AS event,
  jobfull.builder AS builder,
  jobfull.arch AS arch,
  jobfull.status AS status,
  jobfull.created AS j_created,
  jobfull.updated AS j_updated,
  jobfull.e_id as e_id,
  jobfull.project AS project,
  jobfull.type AS type,
  jobfull.clone AS clone,
  jobfull.target AS target,
  jobfull.mrid AS mrid,
  jobfull.mrclone AS mrclone,
  jobfull.mrbranch AS mrbranch,
  jobfull.revision AS revision,
  jobfull.user AS user,
  jobfull.reason AS reason,
  jobfull.e_created AS e_created,
  jobfull.e_updated AS e_updated
FROM tasks
INNER JOIN jobfull ON tasks.job = jobfull.id;
