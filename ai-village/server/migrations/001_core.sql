-- AI Village · esquema do domínio (uma BD por mundo). Ver docs/ARCHITECTURE.md.
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL, checksum TEXT NOT NULL);

CREATE TABLE accounts (
  id TEXT PRIMARY KEY, world_id TEXT NOT NULL,
  alias TEXT NOT NULL, identity_kind TEXT NOT NULL DEFAULT 'synthetic', status TEXT NOT NULL DEFAULT 'active',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, schema_version INTEGER NOT NULL DEFAULT 1, record_version INTEGER NOT NULL DEFAULT 1);

CREATE TABLE org_units (
  id TEXT PRIMARY KEY, world_id TEXT NOT NULL, account_id TEXT,
  name TEXT NOT NULL, purpose TEXT NOT NULL DEFAULT '',
  parent_unit_id TEXT REFERENCES org_units(id), responsible_agent_id TEXT,
  lifecycle_status TEXT NOT NULL DEFAULT 'active' CHECK (lifecycle_status IN ('active','archived')),
  theme TEXT NOT NULL DEFAULT 'hall', kanji TEXT NOT NULL DEFAULT '', plot INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, schema_version INTEGER NOT NULL DEFAULT 1, record_version INTEGER NOT NULL DEFAULT 1);

CREATE TABLE roles (
  id TEXT PRIMARY KEY, world_id TEXT NOT NULL, account_id TEXT,
  name TEXT NOT NULL, mission TEXT NOT NULL DEFAULT '',
  responsibilities TEXT NOT NULL DEFAULT '[]', limits TEXT NOT NULL DEFAULT '[]',
  default_capability_proposals TEXT NOT NULL DEFAULT '[]',
  parent_role_id TEXT REFERENCES roles(id),
  tier TEXT NOT NULL DEFAULT 'specialist' CHECK (tier IN ('ceo','c_level','director','specialist','orchestrator','control')),
  lifecycle_status TEXT NOT NULL DEFAULT 'active' CHECK (lifecycle_status IN ('active','archived')),
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, schema_version INTEGER NOT NULL DEFAULT 1, record_version INTEGER NOT NULL DEFAULT 1);

CREATE TABLE agents (
  id TEXT PRIMARY KEY, world_id TEXT NOT NULL, account_id TEXT,
  display_name TEXT NOT NULL, title TEXT NOT NULL DEFAULT '',
  org_unit_id TEXT REFERENCES org_units(id), manager_agent_id TEXT REFERENCES agents(id),
  description TEXT NOT NULL DEFAULT '', capability_ids TEXT NOT NULL DEFAULT '[]', policy_ref TEXT,
  lifecycle_status TEXT NOT NULL DEFAULT 'active' CHECK (lifecycle_status IN ('active','deactivated','archived')),
  appearance_ref TEXT, orchestrator_flag INTEGER NOT NULL DEFAULT 0, adapter_config_ref TEXT,
  origin TEXT NOT NULL DEFAULT 'app',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, schema_version INTEGER NOT NULL DEFAULT 1, record_version INTEGER NOT NULL DEFAULT 1);
-- No máximo um orquestrador activo por mundo (CA02): garantido pela BD.
CREATE UNIQUE INDEX one_active_orchestrator ON agents(world_id) WHERE orchestrator_flag = 1 AND lifecycle_status = 'active';

CREATE TABLE agent_roles (
  agent_id TEXT NOT NULL REFERENCES agents(id), role_id TEXT NOT NULL REFERENCES roles(id),
  PRIMARY KEY (agent_id, role_id));

CREATE TABLE permissions (
  id TEXT PRIMARY KEY, world_id TEXT NOT NULL, account_id TEXT,
  principal_id TEXT NOT NULL, resource_scope TEXT NOT NULL, allowed_actions TEXT NOT NULL,
  delegation_limit INTEGER NOT NULL DEFAULT 1, valid_from TEXT NOT NULL, expires_at TEXT,
  granted_by TEXT NOT NULL, revoked_at TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, schema_version INTEGER NOT NULL DEFAULT 1, record_version INTEGER NOT NULL DEFAULT 1);

CREATE TABLE conversations (
  id TEXT PRIMARY KEY, world_id TEXT NOT NULL, account_id TEXT,
  agent_id TEXT NOT NULL REFERENCES agents(id), owner_id TEXT NOT NULL, title TEXT NOT NULL DEFAULT 'Conversa',
  mode TEXT NOT NULL CHECK (mode IN ('demo','real')), model_binding_ref TEXT,
  retention_until TEXT, last_sequence INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, schema_version INTEGER NOT NULL DEFAULT 1, record_version INTEGER NOT NULL DEFAULT 1);

CREATE TABLE messages (
  id TEXT PRIMARY KEY, world_id TEXT NOT NULL, account_id TEXT,
  conversation_id TEXT NOT NULL REFERENCES conversations(id), sequence INTEGER NOT NULL,
  author_type TEXT NOT NULL CHECK (author_type IN ('owner','agent','system')),
  content TEXT, state TEXT NOT NULL DEFAULT 'ok' CHECK (state IN ('ok','blocked','error','cancelled','purged')),
  mode TEXT NOT NULL CHECK (mode IN ('demo','real','system')), provider_ref TEXT,
  task_refs TEXT NOT NULL DEFAULT '[]', evidence_refs TEXT NOT NULL DEFAULT '[]', meta TEXT NOT NULL DEFAULT '{}',
  request_id TEXT, reason_code TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, schema_version INTEGER NOT NULL DEFAULT 1, record_version INTEGER NOT NULL DEFAULT 1,
  UNIQUE (conversation_id, sequence));

CREATE TABLE artifacts (
  id TEXT PRIMARY KEY, world_id TEXT NOT NULL, account_id TEXT,
  name TEXT NOT NULL, kind TEXT NOT NULL, media_type TEXT NOT NULL DEFAULT 'text/plain',
  size_bytes INTEGER NOT NULL, digest TEXT NOT NULL, content TEXT,
  classification TEXT NOT NULL DEFAULT 'synthetic', retention_until TEXT, purged_at TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, schema_version INTEGER NOT NULL DEFAULT 1, record_version INTEGER NOT NULL DEFAULT 1);

CREATE TABLE tasks (
  id TEXT PRIMARY KEY, world_id TEXT NOT NULL, account_id TEXT,
  title TEXT NOT NULL, objective TEXT NOT NULL DEFAULT '',
  kind TEXT NOT NULL DEFAULT 'manual', capability TEXT,
  input_refs TEXT NOT NULL DEFAULT '[]', config TEXT NOT NULL DEFAULT '{}',
  expected_output TEXT NOT NULL DEFAULT '', acceptance_refs TEXT NOT NULL DEFAULT '[]',
  owner_id TEXT NOT NULL, assigned_agent_id TEXT REFERENCES agents(id), delegated_by TEXT,
  parent_task_id TEXT REFERENCES tasks(id), scope_ref TEXT,
  proposed_priority INTEGER NOT NULL DEFAULT 3 CHECK (proposed_priority BETWEEN 1 AND 5),
  approved_priority INTEGER CHECK (approved_priority BETWEEN 1 AND 5),
  state TEXT NOT NULL DEFAULT 'draft' CHECK (state IN ('draft','pending','assigned','running','awaiting_approval','completed','blocked','failed','cancelled')),
  idempotency_key TEXT, payload_digest TEXT, result_refs TEXT NOT NULL DEFAULT '[]', error_code TEXT,
  depth INTEGER NOT NULL DEFAULT 0, due_at TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, schema_version INTEGER NOT NULL DEFAULT 1, record_version INTEGER NOT NULL DEFAULT 1);
CREATE UNIQUE INDEX task_idem ON tasks(account_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX task_state ON tasks(state, assigned_agent_id);

CREATE TABLE execution_attempts (
  id TEXT PRIMARY KEY, world_id TEXT NOT NULL, account_id TEXT,
  task_id TEXT NOT NULL REFERENCES tasks(id), attempt_no INTEGER NOT NULL,
  state TEXT NOT NULL CHECK (state IN ('running','succeeded','failed','abandoned','cancelled')),
  executor_ref TEXT NOT NULL, lease_expires_at TEXT, heartbeat_at TEXT, checkpoint TEXT NOT NULL DEFAULT '{}',
  started_at TEXT NOT NULL, ended_at TEXT, error_code TEXT, error_message TEXT, result_ref TEXT, retry_of TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, schema_version INTEGER NOT NULL DEFAULT 1, record_version INTEGER NOT NULL DEFAULT 1,
  UNIQUE (task_id, attempt_no));
-- No máximo uma tentativa activa por tarefa.
CREATE UNIQUE INDEX one_running_attempt ON execution_attempts(task_id) WHERE state = 'running';

CREATE TABLE evidence (
  id TEXT PRIMARY KEY, world_id TEXT NOT NULL, account_id TEXT,
  task_id TEXT NOT NULL REFERENCES tasks(id), attempt_id TEXT REFERENCES execution_attempts(id),
  kind TEXT NOT NULL, input_digest TEXT, artifact_id TEXT REFERENCES artifacts(id), output_digest TEXT,
  executor_ref TEXT NOT NULL, executed_steps TEXT NOT NULL DEFAULT '[]', captured_at TEXT NOT NULL,
  source_ref TEXT, source_version TEXT, classification TEXT NOT NULL DEFAULT 'synthetic',
  limitations TEXT NOT NULL DEFAULT '[]', summary TEXT NOT NULL DEFAULT '{}', mode TEXT NOT NULL DEFAULT 'real_execution',
  retention_until TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, schema_version INTEGER NOT NULL DEFAULT 1, record_version INTEGER NOT NULL DEFAULT 1);

CREATE TABLE connections (
  id TEXT PRIMARY KEY, world_id TEXT NOT NULL, account_id TEXT,
  provider_id TEXT NOT NULL, label TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'source',
  adapter_version TEXT, external_account_alias TEXT, capability_manifest TEXT NOT NULL DEFAULT '{}',
  granted_scopes TEXT NOT NULL DEFAULT '[]',
  status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','demo','pending','connected','degraded','blocked','disconnected','revoked')),
  secret_ref TEXT, verified_at TEXT, proof TEXT, freshness_seconds INTEGER NOT NULL DEFAULT 86400,
  revoked_at TEXT, retention_policy_ref TEXT, notes TEXT NOT NULL DEFAULT '', config TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, schema_version INTEGER NOT NULL DEFAULT 1, record_version INTEGER NOT NULL DEFAULT 1);

CREATE TABLE action_intents (
  id TEXT PRIMARY KEY, world_id TEXT NOT NULL, account_id TEXT,
  task_id TEXT REFERENCES tasks(id), operation TEXT NOT NULL, destination TEXT NOT NULL,
  payload TEXT NOT NULL, payload_version INTEGER NOT NULL DEFAULT 1, payload_digest TEXT NOT NULL,
  idempotency_key TEXT NOT NULL, effect TEXT NOT NULL DEFAULT 'simulated',
  state TEXT NOT NULL DEFAULT 'pending_approval' CHECK (state IN ('pending_approval','approved','executed','cancelled','invalidated','failed')),
  approval_id TEXT, result TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, schema_version INTEGER NOT NULL DEFAULT 1, record_version INTEGER NOT NULL DEFAULT 1,
  UNIQUE (account_id, operation, idempotency_key));

CREATE TABLE approvals (
  id TEXT PRIMARY KEY, world_id TEXT NOT NULL, account_id TEXT,
  intent_id TEXT NOT NULL REFERENCES action_intents(id), payload_version INTEGER NOT NULL, payload_digest TEXT NOT NULL,
  summary TEXT NOT NULL, effect TEXT NOT NULL, approver_id TEXT,
  state TEXT NOT NULL DEFAULT 'pending' CHECK (state IN ('proposed','pending','approved','denied','revoked','expired','consumed')),
  requested_at TEXT NOT NULL, decided_at TEXT, expires_at TEXT NOT NULL, consumed_at TEXT, reason TEXT,
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL, schema_version INTEGER NOT NULL DEFAULT 1, record_version INTEGER NOT NULL DEFAULT 1);

-- Efeito simulado: UNIQUE(intent_id) garante, na própria BD, no máximo um efeito por intenção (CA11).
CREATE TABLE action_effects (
  id TEXT PRIMARY KEY, intent_id TEXT NOT NULL UNIQUE REFERENCES action_intents(id),
  world_id TEXT NOT NULL, simulated INTEGER NOT NULL DEFAULT 1, external_calls INTEGER NOT NULL DEFAULT 0,
  detail TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL);

CREATE TABLE audit_events (
  event_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  id TEXT NOT NULL UNIQUE, world_id TEXT NOT NULL,
  actor_ref TEXT NOT NULL, action TEXT NOT NULL, resource_ref TEXT, result TEXT NOT NULL, reason_code TEXT,
  correlation_id TEXT, payload_digest TEXT, approval_ref TEXT,
  prev_hash TEXT NOT NULL, hash TEXT NOT NULL, occurred_at TEXT NOT NULL);
-- Append-only lógico: só o expurgo de retenção (flag explícita) pode apagar.
CREATE TRIGGER audit_no_update BEFORE UPDATE ON audit_events
  BEGIN SELECT RAISE(ABORT, 'audit_events é append-only'); END;
CREATE TRIGGER audit_no_delete BEFORE DELETE ON audit_events
  WHEN COALESCE((SELECT value FROM meta WHERE key='audit_purge'),'0') <> '1'
  BEGIN SELECT RAISE(ABORT, 'audit_events é append-only'); END;

CREATE TABLE tombstones (
  id TEXT PRIMARY KEY, object_type TEXT NOT NULL, object_id TEXT NOT NULL, kind TEXT NOT NULL,
  reason TEXT, occurred_at TEXT NOT NULL);
