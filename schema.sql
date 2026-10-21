-- Минимальная схема, которой достаточно хукам.

CREATE TABLE IF NOT EXISTS projects (
  id         INTEGER PRIMARY KEY,
  slug       TEXT UNIQUE NOT NULL,
  name       TEXT NOT NULL,
  path       TEXT,                   -- абсолютный путь на диске, по нему хуки узнают проект
  status     TEXT DEFAULT 'active',  -- active | paused | done | archive
  priority   INTEGER DEFAULT 2,
  note       TEXT DEFAULT '',        -- «на чём остановились»
  parent_id  INTEGER REFERENCES projects(id),
  updated_at TEXT
);

CREATE TABLE IF NOT EXISTS tasks (
  id         INTEGER PRIMARY KEY,
  project_id INTEGER REFERENCES projects(id),
  title      TEXT NOT NULL,
  status     TEXT DEFAULT 'todo',    -- todo | doing | blocked | done | drop
  priority   INTEGER DEFAULT 2,
  due        TEXT,                   -- YYYY-MM-DD
  tags       TEXT DEFAULT '',
  body       TEXT DEFAULT '',        -- контекст: где лежат файлы, критерий готовности
  parent_id  INTEGER REFERENCES tasks(id),
  created_at TEXT,
  done_at    TEXT
);

CREATE TABLE IF NOT EXISTS entries (
  id         INTEGER PRIMARY KEY,
  ts         TEXT NOT NULL,
  project_id INTEGER REFERENCES projects(id),
  task_id    INTEGER REFERENCES tasks(id),
  kind       TEXT DEFAULT 'note',    -- note | result | decision | blocker
  text       TEXT NOT NULL,
  actor      TEXT DEFAULT 'me'       -- me | claude
);

CREATE TABLE IF NOT EXISTS sessions (
  id         INTEGER PRIMARY KEY,
  project_id INTEGER REFERENCES projects(id),
  cwd        TEXT,
  session_id TEXT,
  started_at TEXT,
  ended_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_tasks_status  ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_project ON tasks(project_id);
CREATE INDEX IF NOT EXISTS idx_entries_ts    ON entries(ts);
