// Camada BI: KPIs da vila e export CSV das vistas em estrela (dim_*/fact_*), prontas para Power BI/Fabric.
// Só metadados operacionais: nunca conteúdo de mensagens, notas ou artefactos.
import { clock, notFound } from '../lib/util.js';

export const EXPORTABLE = ['dim_unit', 'dim_role', 'dim_agent', 'fact_task', 'fact_attempt', 'fact_approval', 'fact_audit', 'fact_message'];

const pct = (arr, p) => {
  if (!arr.length) return null;
  const s = [...arr].sort((a, b) => a - b);
  return s[Math.min(s.length - 1, Math.ceil((p / 100) * s.length) - 1)];
};

export function kpis(w) {
  const db = w.db;
  const byState = Object.fromEntries(db.prepare('SELECT state, COUNT(*) c FROM tasks GROUP BY state').all().map((r) => [r.state, r.c]));
  const total = Object.values(byState).reduce((a, b) => a + b, 0);
  const byKind = db.prepare('SELECT kind, COUNT(*) c FROM tasks GROUP BY kind').all();
  const workload = db.prepare(`SELECT a.id agent_id, a.display_name, a.org_unit_id,
      SUM(CASE WHEN t.state IN ('assigned','running','awaiting_approval') THEN 1 ELSE 0 END) open_tasks,
      SUM(CASE WHEN t.state='completed' THEN 1 ELSE 0 END) completed_tasks,
      SUM(CASE WHEN t.state IN ('failed','blocked') THEN 1 ELSE 0 END) problem_tasks
    FROM agents a LEFT JOIN tasks t ON t.assigned_agent_id = a.id
    WHERE a.world_id = ? AND a.lifecycle_status <> 'archived' GROUP BY a.id ORDER BY open_tasks DESC, completed_tasks DESC`).all(w.id);
  const durations = db.prepare("SELECT duration_ms d FROM fact_attempt WHERE state='succeeded' AND duration_ms IS NOT NULL").all().map((r) => r.d);
  const lead = db.prepare('SELECT lead_time_seconds s FROM fact_task WHERE lead_time_seconds IS NOT NULL').all().map((r) => r.s);
  const since = new Date(clock.now() - 14 * 86400000).toISOString();
  const daily = db.prepare(`SELECT substr(updated_at,1,10) day, COUNT(*) completed FROM tasks WHERE state='completed' AND updated_at >= ? GROUP BY day ORDER BY day`).all(since);
  const approvals = Object.fromEntries(db.prepare('SELECT state, COUNT(*) c FROM approvals GROUP BY state').all().map((r) => [r.state, r.c]));
  const completed = byState.completed || 0;
  const withEvidence = db.prepare("SELECT COUNT(DISTINCT t.id) c FROM tasks t JOIN evidence e ON e.task_id=t.id WHERE t.state='completed'").get().c;
  const agentStates = db.prepare(`SELECT lifecycle_status s, COUNT(*) c FROM agents WHERE world_id=? GROUP BY lifecycle_status`).all(w.id);
  return {
    generated_at: clock.iso(),
    tasks_total: total,
    tasks_by_state: byState,
    tasks_by_kind: byKind,
    workload,
    attempt_duration_ms: { n: durations.length, p50: pct(durations, 50), p95: pct(durations, 95) },
    lead_time_seconds: { n: lead.length, p50: pct(lead, 50), p95: pct(lead, 95) },
    completed_per_day: daily,
    approvals_by_state: approvals,
    evidence_coverage: completed ? Math.round((withEvidence / completed) * 1000) / 10 : null,
    agents: { total: agentStates.reduce((a, b) => a + b.c, 0), by_lifecycle: Object.fromEntries(agentStates.map((r) => [r.s, r.c])) },
    audit_events: db.prepare('SELECT COUNT(*) c FROM audit_events').get().c,
  };
}

const csvCell = (v) => {
  if (v === null || v === undefined) return '';
  let s = String(v);
  // Anti-injecção de fórmulas ao abrir no Excel/Power BI: prefixar com apóstrofo.
  if (/^[=+\-@\t\r]/.test(s) && !/^-?\d+(\.\d+)?$/.test(s)) s = `'${s}`;
  return /[",\n\r;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

export function exportCsv(w, table) {
  if (!EXPORTABLE.includes(table)) throw notFound('Tabela não exportável');
  const rows = w.db.prepare(`SELECT * FROM ${table}`).all();
  const cols = rows.length ? Object.keys(rows[0]) : w.db.prepare(`PRAGMA table_info(${table})`).all().map((c) => c.name);
  return '﻿' + [cols.join(','), ...rows.map((r) => cols.map((c) => csvCell(r[c])).join(','))].join('\r\n') + '\r\n';
}
