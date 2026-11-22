import { useMemo, useState } from "react";
import { exportUrl } from "../api";
import { formatDate, formatValue } from "../lib/format";
import type { AgentResult, Block } from "../types";
import { ChartBlock, Heatmap } from "./Charts";
import { Icon } from "./Icon";
import { TermChip, TermList } from "./TermChip";
import { Badge, Callout, CodeBlock, Markdown, Stars } from "./ui";

const BADGE_TONE: Record<string, "ok" | "warn" | "crit" | "info" | "blue"> = {
  crítico: "crit", critico: "crit", alto: "crit", significativo: "crit", médio: "warn", moderado: "warn", atenção: "warn",
  baixo: "ok", estável: "ok", "em falta": "crit",
};

function Cell({ value, fmt }: { value: any; fmt?: string }) {
  if (fmt === "badge") return value ? <Badge tone={BADGE_TONE[String(value).toLowerCase()] ?? "info"}>{String(value)}</Badge> : null;
  if (fmt === "term") return value ? <TermChip id={String(value)} /> : null;
  if (fmt === "stars") return typeof value === "number" ? <Stars n={value} /> : null;
  if (typeof value === "boolean") return <>{value ? "sim" : "não"}</>;
  return <>{formatValue(value, fmt)}</>;
}

export function TableBlock({ block, maxHeight }: { block: Block; maxHeight?: number }) {
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);
  const [filter, setFilter] = useState("");
  const columns: { key: string; label: string; fmt?: string }[] = block.columns ?? [];
  const rows = useMemo(() => {
    let r: any[] = block.rows ?? [];
    if (filter) {
      const f = filter.toLowerCase();
      r = r.filter((row) => Object.values(row).some((v) => String(v ?? "").toLowerCase().includes(f)));
    }
    if (sort) {
      r = [...r].sort((a, b) => {
        const va = a[sort.key], vb = b[sort.key];
        if (typeof va === "number" && typeof vb === "number") return (va - vb) * sort.dir;
        return String(va ?? "").localeCompare(String(vb ?? ""), "pt") * sort.dir;
      });
    }
    return r;
  }, [block.rows, sort, filter]);
  if (!columns.length) return <div className="muted small">Sem linhas.</div>;
  const numeric = (c: { key: string; fmt?: string }) => ["num", "int", "pct", "money"].includes(c.fmt ?? "") || typeof rows[0]?.[c.key] === "number";
  return (
    <div className="stack tight">
      {(block.rows?.length ?? 0) > 12 && (
        <div className="row"><input className="input" style={{ maxWidth: 260 }} placeholder="Filtrar linhas…" value={filter} onChange={(e) => setFilter(e.target.value)} />
          <span className="muted tiny">{rows.length} de {block.rows.length} linhas</span></div>
      )}
      <div className="table-wrap" style={maxHeight ? { maxHeight } : undefined}>
        <table className="tbl">
          <thead>
            <tr>
              {columns.map((c) => (
                <th key={c.key} onClick={() => setSort((s) => ({ key: c.key, dir: s?.key === c.key && s.dir === 1 ? -1 : 1 }))} style={{ cursor: "pointer" }}>
                  {c.label}{sort?.key === c.key ? (sort.dir === 1 ? " ▲" : " ▼") : ""}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i}>{columns.map((c) => <td key={c.key} className={numeric(c) ? "num" : ""}><Cell value={row[c.key]} fmt={c.fmt} /></td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function KpiBlock({ block }: { block: Block }) {
  return (
    <div className="kpis">
      {(block.items ?? []).map((k: any, i: number) => (
        <div key={i} className={`kpi ${k.status ?? ""}`}>
          <div className="kpi-label">{k.label}{k.term && <TermChip id={k.term} label="?" />}</div>
          <div className={`kpi-value ${k.fmt === "text" || k.fmt === "status" || typeof k.value === "string" ? "text" : ""}`}>
            {k.fmt === "status" ? <Badge tone={BADGE_TONE[String(k.value)] ?? "info"}>{String(k.value)}</Badge> : formatValue(k.value, k.fmt)}
          </div>
          {k.hint && <div className="kpi-hint">{k.hint}</div>}
        </div>
      ))}
    </div>
  );
}

function ParamsBlock({ block }: { block: Block }) {
  return (
    <div className="stack tight">
      <div className="table-wrap">
        <table className="tbl">
          <thead><tr><th>Parâmetro</th><th>Valor</th><th>Porquê</th><th>Importância</th></tr></thead>
          <tbody>
            {(block.details ?? []).map((d: any) => (
              <tr key={d.name}>
                <td><div style={{ fontWeight: 600 }}>{d.label}</div><code>{d.name}</code> {d.term && <TermChip id={d.term} label="?" />}</td>
                <td className="num"><b>{String(d.value)}</b>{d.changed && <div className="tiny muted">padrão: {String(d.default)}</div>}</td>
                <td className="small">{d.reason}</td>
                <td><Badge tone={d.importance === "alta" ? "crit" : d.importance === "média" ? "warn" : undefined}>{d.importance}</Badge></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(block.notes ?? []).map((n: string, i: number) => <div key={i} className="small muted">• {n}</div>)}
    </div>
  );
}

export function BlockView({ block }: { block: Block }) {
  let body: React.ReactNode = null;
  switch (block.type) {
    case "kpis": body = <KpiBlock block={block} />; break;
    case "table": body = <TableBlock block={block} />; break;
    case "chart": body = <ChartBlock block={block} />; break;
    case "heatmap": body = <Heatmap block={block} />; break;
    case "markdown": body = <Markdown text={block.text ?? ""} />; break;
    case "callout": return <div className="block"><Callout level={block.level} title={block.title}>{block.text} <TermList ids={block.terms} /></Callout></div>;
    case "code": body = <CodeBlock code={block.code ?? ""} language={block.language} />; break;
    case "params": body = <ParamsBlock block={block} />; break;
    case "download":
      body = <div className="row">{(block.files ?? []).map((f: any) => (
        <a key={f.path} className="btn sm" href={exportUrl(f.path)} download><Icon name="download" size={14} />{f.label}</a>))}</div>;
      break;
    default: body = <pre className="small">{JSON.stringify(block, null, 2)}</pre>;
  }
  return (
    <div className="block">
      {block.title && <div className="block-title">{block.title}<TermList ids={block.terms} max={4} /></div>}
      {block.description && <div className="muted small" style={{ marginBottom: 6 }}>{block.description}</div>}
      {body}
    </div>
  );
}

export function AgentResultView({ result, compact }: { result: AgentResult; compact?: boolean }) {
  const tone = result.status === "ok" ? "ok" : result.status === "warning" ? "warn" : "crit";
  return (
    <div className="stack">
      <div className="result-head">
        <div style={{ minWidth: 0 }}>
          <div className="row"><Badge tone={tone}>{result.status === "ok" ? "Concluído" : result.status === "warning" ? "Concluído com avisos" : "Erro"}</Badge>
            <span className="muted tiny">{formatDate(result.created_at)} · {(result.duration_ms / 1000).toFixed(1)} s</span></div>
          <div style={{ marginTop: 6 }}><Markdown text={result.summary} /></div>
        </div>
        <TermList ids={result.terms} max={6} />
      </div>
      {result.insights.length > 0 && (
        <div className="insights">
          {result.insights.map((i, k) => (
            <Callout key={k} level={i.level} title={i.title}>{i.detail} <TermList ids={i.terms} max={3} /></Callout>
          ))}
        </div>
      )}
      {result.recommendations.length > 0 && (
        <Callout level="info" title="Recomendações">
          <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>{result.recommendations.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </Callout>
      )}
      {!compact && result.blocks.map((b, i) => <BlockView key={i} block={b} />)}
    </div>
  );
}
