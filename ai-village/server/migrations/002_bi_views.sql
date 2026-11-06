-- Camada BI: vistas em estrela (dimensões + factos) prontas para Power BI/Fabric via export CSV.
-- Só metadados operacionais; nunca conteúdo de mensagens nem artefactos.
CREATE VIEW dim_unit AS
  SELECT id AS unit_id, name AS unit_name, purpose, parent_unit_id, responsible_agent_id, lifecycle_status FROM org_units;

CREATE VIEW dim_role AS
  SELECT id AS role_id, name AS role_name, tier, parent_role_id, lifecycle_status FROM roles;

CREATE VIEW dim_agent AS
  SELECT a.id AS agent_id, a.display_name, a.title, a.org_unit_id AS unit_id, a.manager_agent_id,
         a.lifecycle_status, a.orchestrator_flag, a.origin,
         (SELECT group_concat(r.name, ' | ') FROM agent_roles ar JOIN roles r ON r.id = ar.role_id WHERE ar.agent_id = a.id) AS roles
  FROM agents a;

CREATE VIEW fact_task AS
  SELECT t.id AS task_id, t.title, t.kind, t.capability, t.state, t.assigned_agent_id AS agent_id,
         t.delegated_by, t.parent_task_id, t.proposed_priority, t.approved_priority, t.depth,
         t.created_at, t.updated_at, t.error_code,
         (SELECT COUNT(*) FROM execution_attempts x WHERE x.task_id = t.id) AS attempts,
         (SELECT COUNT(*) FROM evidence e WHERE e.task_id = t.id) AS evidence_count,
         CASE WHEN t.state IN ('completed','failed','cancelled')
              THEN CAST(ROUND((julianday(t.updated_at) - julianday(t.created_at)) * 86400) AS INTEGER) END AS lead_time_seconds
  FROM tasks t;

CREATE VIEW fact_attempt AS
  SELECT x.id AS attempt_id, x.task_id, x.attempt_no, x.state, x.executor_ref, x.started_at, x.ended_at, x.error_code,
         CASE WHEN x.ended_at IS NOT NULL
              THEN CAST(ROUND((julianday(x.ended_at) - julianday(x.started_at)) * 86400000) AS INTEGER) END AS duration_ms
  FROM execution_attempts x;

CREATE VIEW fact_approval AS
  SELECT p.id AS approval_id, p.intent_id, p.state, p.effect, p.requested_at, p.decided_at, p.expires_at, p.consumed_at,
         CASE WHEN p.decided_at IS NOT NULL
              THEN CAST(ROUND((julianday(p.decided_at) - julianday(p.requested_at)) * 86400) AS INTEGER) END AS decision_seconds
  FROM approvals p;

CREATE VIEW fact_audit AS
  SELECT event_sequence, actor_ref, action, resource_ref, result, reason_code, occurred_at FROM audit_events;

CREATE VIEW fact_message AS
  SELECT m.id AS message_id, c.agent_id, m.conversation_id, m.sequence, m.author_type, m.state, m.mode, m.created_at,
         LENGTH(COALESCE(m.content,'')) AS content_chars
  FROM messages m JOIN conversations c ON c.id = m.conversation_id;
