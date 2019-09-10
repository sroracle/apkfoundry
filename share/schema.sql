PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS builders (
  builder     TEXT PRIMARY KEY,
  online      BOOLEAN,
  updated     TIMESTAMP NOT NULL
    DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER IF NOT EXISTS builders_timestamp
  AFTER UPDATE ON builders
FOR EACH ROW BEGIN
  UPDATE builders SET updated = CURRENT_TIMESTAMP WHERE builder = OLD.builder;
END;

CREATE TABLE IF NOT EXISTS arches (
  builder     TEXT NOT NULL,
  arch        TEXT NOT NULL,
  idle        BOOLEAN,
  PRIMARY KEY(builder, arch),
  FOREIGN KEY(builder) REFERENCES builders(builder)
);

CREATE TRIGGER IF NOT EXISTS arches_builders
  BEFORE INSERT ON arches
FOR EACH ROW WHEN
  CASE NEW.builder
  WHEN NULL
  THEN NOT EXISTS (SELECT 1 FROM builders WHERE builder IS NULL)
  ELSE TRUE
  END
BEGIN
  INSERT OR IGNORE INTO builders (builder) VALUES (NEW.builder);
END;

CREATE TABLE IF NOT EXISTS events (
  eventid     INTEGER PRIMARY KEY,
  project     TEXT    NOT NULL,
  type        INT     NOT NULL,
  clone       TEXT    NOT NULL,
  target      TEXT    NOT NULL,
  revision    TEXT    NOT NULL,
  user        TEXT    NOT NULL,
  reason      TEXT    NOT NULL,
  status      INT     NOT NULL
    DEFAULT 1,
  created     TIMESTAMP NOT NULL
    DEFAULT CURRENT_TIMESTAMP,
  updated     TIMESTAMP NOT NULL
    DEFAULT CURRENT_TIMESTAMP,
  mrid        INT,
  mrclone     TEXT,
  mrbranch    TEXT
);

CREATE TRIGGER IF NOT EXISTS events_timestamp
  AFTER UPDATE ON events
FOR EACH ROW BEGIN
  UPDATE events SET updated = CURRENT_TIMESTAMP WHERE eventid = OLD.eventid;
END;

CREATE TABLE IF NOT EXISTS jobs (
  jobid       INTEGER PRIMARY KEY,
  eventid     INTEGER NOT NULL,
  builder     TEXT,
  arch        TEXT    NOT NULL,
  status      INT     NOT NULL
    DEFAULT 1,
  created     TIMESTAMP NOT NULL
    DEFAULT CURRENT_TIMESTAMP,
  updated     TIMESTAMP NOT NULL
    DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(eventid) REFERENCES events(eventid),
  FOREIGN KEY(builder) REFERENCES builders(builder)
);

CREATE TRIGGER IF NOT EXISTS jobs_timestamp
  AFTER UPDATE ON jobs
FOR EACH ROW BEGIN
  UPDATE jobs SET updated = CURRENT_TIMESTAMP WHERE jobid = OLD.jobid;
END;

CREATE TRIGGER IF NOT EXISTS jobs_status
  AFTER UPDATE OF status ON jobs
FOR EACH ROW BEGIN
  UPDATE events SET status =
    CASE
    WHEN NOT EXISTS
      -- (1, 4) = (new, start)
      (SELECT 1 FROM jobs WHERE status IN (1, 4) AND eventid = NEW.eventid)
    THEN
        CASE
        WHEN 56 IN (SELECT DISTINCT status FROM jobs WHERE eventid = NEW.eventid)
        THEN 56 -- cancel
        WHEN 24 IN (SELECT DISTINCT status FROM jobs WHERE eventid = NEW.eventid)
        THEN 24 -- error
        WHEN 152 IN (SELECT DISTINCT status FROM jobs WHERE eventid = NEW.eventid)
        THEN 152 -- fail
        WHEN 312 IN (SELECT DISTINCT status FROM jobs WHERE eventid = NEW.eventid)
        THEN 312 -- depfail
        ELSE 72 -- success
        END
    -- if the event is currently new then start it
    WHEN status = 1 AND NEW.status != 1
    THEN 4
    -- otherwise no change
    ELSE status
    END
  WHERE eventid = NEW.eventid;
END;

CREATE TRIGGER IF NOT EXISTS jobs_builders
  BEFORE UPDATE OF builder ON jobs
FOR EACH ROW WHEN
  CASE NEW.builder
  WHEN NULL
  THEN NOT EXISTS (SELECT 1 FROM arches WHERE builder IS NULL AND arch = NEW.arch)
  ELSE TRUE
  END
BEGIN
  INSERT OR IGNORE INTO arches (builder, arch) VALUES (NEW.builder, NEW.arch);
END;

CREATE TABLE IF NOT EXISTS tasks (
  taskid      INTEGER PRIMARY KEY,
  jobid       INTEGER NOT NULL,
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
  FOREIGN KEY(jobid) REFERENCES jobs(jobid)
);

CREATE TRIGGER IF NOT EXISTS tasks_timestamp
  AFTER UPDATE ON tasks
FOR EACH ROW BEGIN
  UPDATE tasks SET updated = CURRENT_TIMESTAMP WHERE taskid = OLD.taskid;
END;

CREATE TRIGGER IF NOT EXISTS tasks_status
  AFTER UPDATE OF status ON tasks
FOR EACH ROW BEGIN
  UPDATE jobs SET status =
    CASE
    WHEN NOT EXISTS
      -- (1, 4) = (new, start)
      (SELECT 1 FROM tasks WHERE status IN (1, 4) AND jobid = NEW.jobid)
    THEN
        CASE
        WHEN 56 IN (SELECT DISTINCT status FROM tasks WHERE jobid = NEW.jobid)
        THEN 56 -- cancel
        WHEN 24 IN (SELECT DISTINCT status FROM tasks WHERE jobid = NEW.jobid)
        THEN 24 -- error
        WHEN 152 IN (SELECT DISTINCT status FROM tasks WHERE jobid = NEW.jobid)
        THEN 152 -- fail
        WHEN 312 IN (SELECT DISTINCT status FROM tasks WHERE jobid = NEW.jobid)
        THEN 312 -- depfail
        ELSE 72 -- success
        END
    -- if the job is currently new then start it
    WHEN status = 1 AND NEW.status != 1
    THEN 4
    -- otherwise no change
    ELSE status
    END
  WHERE jobid = NEW.jobid;
END;

CREATE VIEW IF NOT EXISTS jobs_full AS
SELECT
  jobs.jobid AS jobid,
  jobs.eventid AS eventid,
  jobs.builder AS builder,
  jobs.arch AS arch,
  jobs.status AS status,
  jobs.created AS created,
  jobs.updated AS updated,
  events.project AS project,
  events.type AS type,
  events.clone AS clone,
  events.target AS target,
  events.mrid AS mrid,
  events.mrclone AS mrclone,
  events.mrbranch AS mrbranch,
  events.revision AS revision,
  events.user AS user,
  events.reason AS reason
FROM jobs
INNER JOIN events ON jobs.eventid = events.eventid;

CREATE VIEW IF NOT EXISTS tasks_full AS
SELECT
  tasks.taskid AS taskid,
  tasks.jobid AS jobid,
  tasks.repo AS repo,
  tasks.pkg AS pkg,
  tasks.maintainer AS maintainer,
  tasks.status AS status,
  tasks.tail AS tail,
  tasks.created AS created,
  tasks.updated AS updated,
  jobs_full.eventid AS eventid,
  jobs_full.builder AS builder,
  jobs_full.arch AS arch,
  jobs_full.status AS status,
  jobs_full.project AS project,
  jobs_full.type AS type,
  jobs_full.clone AS clone,
  jobs_full.target AS target,
  jobs_full.mrid AS mrid,
  jobs_full.mrclone AS mrclone,
  jobs_full.mrbranch AS mrbranch,
  jobs_full.revision AS revision,
  jobs_full.user AS user,
  jobs_full.reason AS reason
FROM tasks
INNER JOIN jobs_full ON tasks.jobid = jobs_full.jobid;
