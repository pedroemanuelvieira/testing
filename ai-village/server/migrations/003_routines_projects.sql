-- Rotinas agendadas e projetos (incl. ML). As rotinas NÃO são executadas pela app: são registos de
-- execuções que correm noutro ambiente (Dojo/tenant), introduzidos à mão ou importados, higienizados (D1).
CREATE TABLE projects (
  id TEXT PRIMARY KEY, world_id TEXT NOT NULL, account_id TEXT,
  number TEXT NOT NULL DEFAULT '', title TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'general' CHECK (kind IN ('ml','general')),
  state TEXT NOT NULL DEFAULT 'active' CHECK (state IN ('active','paused','done','in_production','preparing','blocked','on_demand')),
  cadence TEXT NOT NULL DEFAULT '', last_point TEXT NOT NULL DEFAULT '',
  last_point_status TEXT NOT NULL DEFAULT 'none' CHECK (last_point_status IN ('ok','warn','failed','none')),
  next_step TEXT NOT NULL DEFAULT '', owner_agent_id TEXT REFERENCES agents(id),
  lifecycle_status TEXT NOT NULL DEFAULT 'active' CHECK (lifecycle_status IN ('active','archived')),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, schema_version INTEGER NOT NULL DEFAULT 1, record_version INTEGER NOT NULL DEFAULT 1);

ALTER TABLE tasks ADD COLUMN project_id TEXT REFERENCES projects(id);

CREATE TABLE routines (
  id TEXT PRIMARY KEY, world_id TEXT NOT NULL, account_id TEXT,
  agent_id TEXT NOT NULL REFERENCES agents(id), project_id TEXT REFERENCES projects(id),
  title TEXT NOT NULL, schedule TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1,
  lifecycle_status TEXT NOT NULL DEFAULT 'active' CHECK (lifecycle_status IN ('active','archived')),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, schema_version INTEGER NOT NULL DEFAULT 1, record_version INTEGER NOT NULL DEFAULT 1);

CREATE TABLE routine_runs (
  id TEXT PRIMARY KEY, world_id TEXT NOT NULL, account_id TEXT,
  routine_id TEXT NOT NULL REFERENCES routines(id), slot_at TEXT, recorded_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('ok','warn','failed')), note TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT 'manual' CHECK (source IN ('manual','import')),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, schema_version INTEGER NOT NULL DEFAULT 1, record_version INTEGER NOT NULL DEFAULT 1);
-- Uma execução registada por slot agendado (evita duplicar registos).
CREATE UNIQUE INDEX one_run_per_slot ON routine_runs(routine_id, slot_at) WHERE slot_at IS NOT NULL;

CREATE VIEW dim_project AS
  SELECT id AS project_id, number, title, kind, state, cadence, last_point_status, owner_agent_id AS agent_id, lifecycle_status FROM projects;
CREATE VIEW dim_routine AS
  SELECT id AS routine_id, agent_id, project_id, title, schedule, enabled, lifecycle_status FROM routines;
CREATE VIEW fact_routine_run AS
  SELECT x.id AS run_id, x.routine_id, r.agent_id, r.project_id, x.slot_at, x.recorded_at, x.status, x.source,
         CASE WHEN x.slot_at IS NOT NULL THEN CAST(ROUND((julianday(x.recorded_at) - julianday(x.slot_at)) * 1440) AS INTEGER) END AS delay_minutes
  FROM routine_runs x JOIN routines r ON r.id = x.routine_id;
