import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { TableBlock } from "../components/Blocks";
import { Icon } from "../components/Icon";
import { TermChip } from "../components/TermChip";
import { Badge, Callout, Empty, ErrorBox, Modal, Spinner, Tabs } from "../components/ui";
import { useApp, useFetch } from "../lib/context";
import { PROBLEM_LABEL } from "../lib/format";
import type { Connector, ProblemType, ProjectView, UseCase } from "../types";

interface WS { id: string; name: string; description?: string }
interface DS { id: string; name: string; description?: string; tables?: number }
interface TableInfo { name: string; row_count?: number; columns: { name: string; data_type: string }[] }
interface FilterRow { column: string; op: string; value: string }

export default function DataHub() {
  const { meta, refreshMeta } = useApp();
  const nav = useNavigate();
  const conns = useFetch<{ connectors: Connector[]; default: string }>("/api/connectors");
  const [cid, setCid] = useState<string>("");
  const [test, setTest] = useState<any>(null);
  const [workspaces, setWorkspaces] = useState<WS[]>([]);
  const [datasets, setDatasets] = useState<Record<string, DS[]>>({});
  const [tables, setTables] = useState<Record<string, TableInfo[]>>({});
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [sel, setSel] = useState<{ ws: WS; ds: DS; table: TableInfo } | null>(null);
  const [tab, setTab] = useState<"preview" | "dax" | "columns">("preview");
  const [preview, setPreview] = useState<any>(null);
  const [dax, setDax] = useState("");
  const [filters, setFilters] = useState<FilterRow[]>([]);
  const [top, setTop] = useState(100);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [uploadMsg, setUploadMsg] = useState<string | null>(null);

  useEffect(() => { if (conns.data && !cid) setCid(conns.data.default); }, [conns.data, cid]);
  useEffect(() => {
    if (!cid) return;
    setWorkspaces([]); setDatasets({}); setTables({}); setSel(null); setPreview(null); setTest(null); setErr(null);
    api.get<any>(`/api/connectors/${cid}/test`).then(setTest).catch(setErr);
    api.get<WS[]>(`/api/connectors/${cid}/workspaces`).then(setWorkspaces).catch(setErr);
  }, [cid]);

  async function toggleWs(ws: WS) {
    setOpen((o) => ({ ...o, [ws.id]: !o[ws.id] }));
    if (!datasets[ws.id]) api.get<DS[]>(`/api/connectors/${cid}/workspaces/${ws.id}/datasets`).then((d) => setDatasets((s) => ({ ...s, [ws.id]: d }))).catch(setErr);
  }
  async function toggleDs(ws: WS, ds: DS) {
    const key = `${ws.id}/${ds.id}`;
    setOpen((o) => ({ ...o, [key]: !o[key] }));
    if (!tables[key]) api.get<TableInfo[]>(`/api/connectors/${cid}/workspaces/${ws.id}/datasets/${ds.id}/tables`).then((t) => setTables((s) => ({ ...s, [key]: t }))).catch(setErr);
  }
  async function runQuery(custom?: boolean, s = sel) {
    if (!s) return;
    setBusy(true); setErr(null);
    try {
      const body: any = { workspace_id: s.ws.id, dataset_id: s.ds.id, top };
      if (custom) body.query = dax;
      else { body.table = s.table.name; body.filters = filters.filter((f) => f.column && f.value !== "").map((f) => ({ ...f, value: isNaN(Number(f.value)) ? f.value : Number(f.value) })); }
      const r = await api.post<any>(`/api/connectors/${cid}/query`, body);
      setPreview(r);
      if (!custom) setDax(r.dax);
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }
  function selectTable(ws: WS, ds: DS, table: TableInfo) {
    const s = { ws, ds, table };
    setSel(s); setFilters([]); setTab("preview");
    void runQuery(false, s);
  }
  async function upload(file: File) {
    const form = new FormData();
    form.append("file", file);
    setBusy(true); setErr(null);
    try {
      const r = await api.upload<any>("/api/connectors/files/upload", form);
      setUploadMsg(`"${file.name}" carregado como tabela '${r.table}' (${r.rows} linhas).`);
      setCid("files");
      if (cid === "files") { setCid(""); setTimeout(() => setCid("files"), 0); }
      refreshMeta();
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }

  const conn = conns.data?.connectors.find((c) => c.id === cid);
  return (
    <div className="stack">
      <div className="page-head">
        <div><h1>Dados — Power BI Service</h1>
          <p>Navegue pelos workspaces e modelos semânticos através do conector, pré-visualize tabelas, gere ou escreva consultas
            DAX e crie projetos com a fonte certa. <TermChip id="modelo_semantico" /> <TermChip id="evaluate_dax" /> <TermChip id="granularidade" /></p></div>
        <label className="btn"><Icon name="upload" size={15} />Carregar CSV/Excel
          <input type="file" accept=".csv,.txt,.xlsx,.xls,.parquet" hidden onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} /></label>
      </div>
      {uploadMsg && <Callout level="success" title="Ficheiro carregado">{uploadMsg}</Callout>}
      {meta && !meta.connectors.some((c) => c.kind === "internal") && (
        <Callout level="info" title="A usar o conector de demonstração">
          Para ligar ao vosso Power BI Service, configure o conector interno com <code>MLSTUDIO_INTERNAL_CONNECTOR=pacote.modulo:Classe</code>
          (ver <code>docs/CONECTOR_POWERBI.md</code>) ou a API REST oficial com um <TermChip id="service_principal" />.
        </Callout>
      )}
      <div className="grid" style={{ gridTemplateColumns: "minmax(260px, 320px) minmax(0, 1fr)", alignItems: "start" }}>
        <div className="card stack" style={{ padding: 12 }}>
          <label className="field">Conector
            <select className="select" value={cid} onChange={(e) => setCid(e.target.value)}>
              {(conns.data?.connectors ?? []).filter((c) => c.status === "ok").map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          {conn && <div className="row">{conn.capabilities.map((c) => <Badge key={c} tone="blue">{c}</Badge>)}</div>}
          {test && <Callout level={test.ok ? "success" : "critical"} title={test.ok ? "Ligação OK" : "Falha na ligação"}>{test.message}</Callout>}
          <div className="tree">
            {workspaces.map((ws) => (
              <div key={ws.id}>
                <button className="tree-item" onClick={() => toggleWs(ws)}><Icon name={open[ws.id] ? "chevron-down" : "chevron-right"} size={14} /><Icon name="folder" size={15} />{ws.name}</button>
                {open[ws.id] && (datasets[ws.id] ?? []).map((ds) => {
                  const key = `${ws.id}/${ds.id}`;
                  return (
                    <div key={ds.id} style={{ paddingLeft: 16 }}>
                      <button className="tree-item" onClick={() => toggleDs(ws, ds)} title={ds.description}>
                        <Icon name={open[key] ? "chevron-down" : "chevron-right"} size={14} /><Icon name="database" size={14} />{ds.name}</button>
                      {open[key] && (tables[key] ?? []).map((t) => (
                        <button key={t.name} style={{ paddingLeft: 36 }} className={`tree-item ${sel?.table.name === t.name && sel.ds.id === ds.id ? "active" : ""}`}
                          onClick={() => selectTable(ws, ds, t)}>
                          <Icon name="table" size={14} />{t.name}{t.row_count != null && <span className="tiny muted" style={{ marginLeft: "auto" }}>{t.row_count.toLocaleString("pt-PT")}</span>}
                        </button>
                      ))}
                      {open[key] && !tables[key] && <div style={{ paddingLeft: 36 }}><Spinner size={13} /></div>}
                    </div>
                  );
                })}
              </div>
            ))}
            {!workspaces.length && !err && <Spinner />}
          </div>
        </div>
        <div className="stack">
          <ErrorBox error={err} />
          {!sel ? (
            <div className="card"><Empty icon="database" title="Escolha uma tabela">Expanda um workspace e um modelo semântico à esquerda.</Empty></div>
          ) : (
            <div className="card">
              <div className="card-title">
                <div><h3>{sel.table.name}</h3><div className="muted small">{sel.ds.name} · {sel.ws.name} · {sel.table.columns.length} colunas{sel.table.row_count != null ? ` · ${sel.table.row_count.toLocaleString("pt-PT")} linhas` : ""}</div></div>
                <button className="btn primary" onClick={() => setCreateOpen(true)}><Icon name="plus" size={15} />Criar projeto com esta tabela</button>
              </div>
              <Tabs value={tab} onChange={setTab} tabs={[{ id: "preview", label: "Pré-visualização" }, { id: "dax", label: "Consulta DAX" }, { id: "columns", label: "Colunas" }]} />
              {tab === "preview" && (
                <div className="stack">
                  <div className="stack tight">
                    {filters.map((f, i) => (
                      <div key={i} className="row">
                        <select className="select" style={{ maxWidth: 220 }} value={f.column} onChange={(e) => setFilters((fs) => fs.map((x, k) => (k === i ? { ...x, column: e.target.value } : x)))}>
                          <option value="">coluna…</option>{sel.table.columns.map((c) => <option key={c.name}>{c.name}</option>)}
                        </select>
                        <select className="select" style={{ maxWidth: 90 }} value={f.op} onChange={(e) => setFilters((fs) => fs.map((x, k) => (k === i ? { ...x, op: e.target.value } : x)))}>
                          {["=", "!=", ">", ">=", "<", "<=", "contains"].map((o) => <option key={o}>{o}</option>)}
                        </select>
                        <input className="input" style={{ maxWidth: 200 }} value={f.value} placeholder="valor" onChange={(e) => setFilters((fs) => fs.map((x, k) => (k === i ? { ...x, value: e.target.value } : x)))} />
                        <button className="icon-btn" onClick={() => setFilters((fs) => fs.filter((_, k) => k !== i))}><Icon name="x" size={15} /></button>
                      </div>
                    ))}
                    <div className="row">
                      <button className="btn sm" onClick={() => setFilters((f) => [...f, { column: "", op: "=", value: "" }])}><Icon name="plus" size={13} />Filtro</button>
                      <label className="row small">Linhas <input className="input" type="number" style={{ width: 90 }} value={top} min={1} max={1000} onChange={(e) => setTop(Number(e.target.value))} /></label>
                      <button className="btn sm primary" onClick={() => runQuery(false)} disabled={busy}>{busy ? <Spinner size={13} /> : <Icon name="play" size={13} />}Atualizar</button>
                    </div>
                  </div>
                  {preview && <TableBlock block={{ type: "table", columns: preview.columns.map((c: any) => ({ key: c.name, label: c.name })), rows: preview.rows }} />}
                </div>
              )}
              {tab === "dax" && (
                <div className="stack">
                  <div className="small muted">Edite a consulta e execute. O conector de demonstração suporta EVALUATE com TOPN, FILTER, SELECTCOLUMNS, CALCULATETABLE e SUMMARIZECOLUMNS.</div>
                  <textarea className="textarea" style={{ minHeight: 180 }} value={dax} onChange={(e) => setDax(e.target.value)} />
                  <div className="row"><button className="btn primary sm" onClick={() => runQuery(true)} disabled={busy || !dax.trim()}><Icon name="play" size={13} />Executar DAX</button></div>
                  {preview && <TableBlock block={{ type: "table", columns: preview.columns.map((c: any) => ({ key: c.name, label: c.name })), rows: preview.rows }} />}
                </div>
              )}
              {tab === "columns" && (
                <TableBlock block={{ type: "table", columns: [{ key: "name", label: "Coluna" }, { key: "data_type", label: "Tipo" }], rows: sel.table.columns }} />
              )}
            </div>
          )}
        </div>
      </div>
      {createOpen && sel && (
        <CreateFromSource onClose={() => setCreateOpen(false)} source={{ connector_id: cid, workspace_id: sel.ws.id, dataset_id: sel.ds.id, table: sel.table.name, filters: [] }}
          tableName={sel.table.name} onCreated={(id) => nav(`/projetos/${id}`)} />
      )}
    </div>
  );
}

export function CreateFromSource({ source, tableName, onClose, onCreated }: { source: any; tableName?: string; onClose: () => void; onCreated: (id: string) => void }) {
  const ucs = useFetch<UseCase[]>("/api/knowledge/use-cases");
  const pts = useFetch<ProblemType[]>("/api/knowledge/problem-types");
  const [name, setName] = useState(tableName ? `Projeto ${tableName}` : "Novo projeto");
  const [uc, setUc] = useState("");
  const [pt, setPt] = useState("binary_classification");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<unknown>(null);
  const suggested = (ucs.data ?? []).filter((u) => u.demo?.table === tableName);
  async function create() {
    setBusy(true);
    try {
      const v = await api.post<ProjectView>("/api/projects", { name, use_case_id: uc || undefined, problem_type: uc ? undefined : pt, source });
      onCreated(v.project.id);
    } catch (e) { setErr(e); } finally { setBusy(false); }
  }
  return (
    <Modal size="sm" title="Criar projeto" subtitle={tableName ? `Fonte: ${tableName}` : undefined} onClose={onClose}
      footer={<><button className="btn" onClick={onClose}>Cancelar</button><button className="btn primary" onClick={create} disabled={busy}>{busy && <Spinner />}Criar</button></>}>
      <div className="stack">
        <ErrorBox error={err} />
        <label className="field">Nome<input className="input" value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label className="field">Caso de uso (especializa os agentes)
          <select className="select" value={uc} onChange={(e) => setUc(e.target.value)}>
            <option value="">— personalizado —</option>
            {suggested.length > 0 && <optgroup label="Sugeridos para esta tabela">{suggested.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</optgroup>}
            <optgroup label="Todos">{(ucs.data ?? []).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}</optgroup>
          </select>
        </label>
        {!uc && (
          <label className="field">Tipo de problema
            <select className="select" value={pt} onChange={(e) => setPt(e.target.value)}>{(pts.data ?? []).map((p) => <option key={p.id} value={p.id}>{p.name} — {p.short}</option>)}</select>
          </label>
        )}
        {!uc && <div className="small muted">Depois de criar, o Agente de Enquadramento ajuda a escolher o alvo ({PROBLEM_LABEL[pt]}).</div>}
      </div>
    </Modal>
  );
}
