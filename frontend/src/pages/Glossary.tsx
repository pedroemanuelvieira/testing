import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { Icon } from "../components/Icon";
import { TermChip, TermList } from "../components/TermChip";
import { Badge, Callout, Empty, Markdown, Spinner, Tabs } from "../components/ui";
import { useApp, useFetch } from "../lib/context";
import { LEVEL_LABEL } from "../lib/format";
import type { GlossaryCategory, Guide, Term, WorkflowStep } from "../types";

const LEVEL_TONE: Record<string, "ok" | "warn" | "crit"> = { básico: "ok", intermédio: "warn", avançado: "crit" };

function TermDetail({ id }: { id: string }) {
  const { data: t, error } = useFetch<Term>(`/api/knowledge/glossary/${id}`);
  const nav = useNavigate();
  const { openChat } = useApp();
  if (error) return <Callout level="warning" title="Termo não encontrado" />;
  if (!t) return <Spinner />;
  return (
    <div className="stack">
      <div>
        <div className="row"><Badge tone={LEVEL_TONE[t.level]}>{LEVEL_LABEL[t.level]}</Badge>{t.en && <span className="small muted"><i>{t.en}</i></span>}</div>
        <h1 style={{ marginTop: 8 }}>{t.term}</h1>
        <p style={{ fontSize: "1.02rem", color: "var(--text-2)" }}>{t.short}</p>
      </div>
      <div className="card flat"><Markdown text={t.definition} /></div>
      {t.formula && <div><b className="small">Fórmula</b><div className="formula">{t.formula}</div></div>}
      {t.example && <Callout level="info" title="Exemplo em contexto de BI">{t.example}</Callout>}
      {t.pitfalls.length > 0 && <Callout level="warning" title="Armadilhas">{t.pitfalls.map((p) => <div key={p}>• {p}</div>)}</Callout>}
      {(t.related_terms ?? []).length > 0 && (
        <div><b className="small">Termos relacionados</b>
          <div className="grid auto-sm" style={{ marginTop: 6 }}>
            {t.related_terms!.map((r) => (
              <div key={r.id} className="card flat" style={{ padding: 10, cursor: "pointer" }} onClick={() => nav(`/glossario/${r.id}`)}>
                <b className="small">{r.term}</b><div className="tiny muted">{r.short}</div>
              </div>
            ))}
          </div>
        </div>
      )}
      {(t.used_in_steps ?? []).length > 0 && (
        <div><b className="small">Onde aparece no percurso</b>
          <div className="row" style={{ marginTop: 6 }}>{t.used_in_steps!.map((s) => (
            <button key={s.id} className="chip" onClick={() => nav(`/glossario?tab=percurso&passo=${s.id}`)}>Passo {s.order}. {s.title}</button>))}</div>
        </div>
      )}
      {(t.used_by_models ?? []).length > 0 && (
        <div><b className="small">Hiperparâmetros relacionados</b>
          <div className="row" style={{ marginTop: 6 }}>{t.used_by_models!.map((m) => (
            <button key={`${m.id}-${m.param}`} className="chip" onClick={() => nav(`/conselheiro?modelo=${m.id}`)}><code>{m.param}</code> em {m.name}</button>))}</div>
        </div>
      )}
      {(t.use_cases ?? []).length > 0 && (
        <div><b className="small">Casos de uso onde é relevante</b>
          <div className="row" style={{ marginTop: 6 }}>{t.use_cases!.map((u) => <button key={u.id} className="chip" onClick={() => nav(`/casos-de-uso?caso=${u.id}`)}>{u.name}</button>)}</div>
        </div>
      )}
      <div><button className="btn" onClick={() => openChat(`Explica-me "${t.term}" com um exemplo do meu dia a dia em BI.`)}><Icon name="message-circle" size={15} />Pedir mais explicações ao assistente</button></div>
    </div>
  );
}

function GlossaryTab() {
  const { termId } = useParams();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("");
  const [level, setLevel] = useState("");
  const cats = useFetch<GlossaryCategory[]>("/api/knowledge/glossary/categories");
  const [terms, setTerms] = useState<Term[] | null>(null);
  useEffect(() => {
    const t = setTimeout(() => {
      const p = new URLSearchParams({ ...(q && { q }), ...(cat && { category: cat }), ...(level && { level }) });
      api.get<Term[]>(`/api/knowledge/glossary?${p}`).then(setTerms).catch(() => setTerms([]));
    }, 150);
    return () => clearTimeout(t);
  }, [q, cat, level]);
  const grouped = useMemo(() => {
    if (!terms) return [];
    if (q) return [["Resultados", terms] as [string, Term[]]];
    const g: Record<string, Term[]> = {};
    for (const t of terms) (g[t.term[0].toUpperCase()] ??= []).push(t);
    return Object.entries(g);
  }, [terms, q]);
  return (
    <div className="grid" style={{ gridTemplateColumns: "minmax(280px, 340px) minmax(0, 1fr)", alignItems: "start" }}>
      <div className="card stack" style={{ padding: 12, position: "sticky", top: 0, maxHeight: "calc(100vh - 170px)", overflow: "hidden" }}>
        <input className="input" placeholder="Pesquisar no glossário (PT ou EN)…" value={q} onChange={(e) => setQ(e.target.value)} />
        <div className="row">
          <select className="select" value={cat} onChange={(e) => setCat(e.target.value)} style={{ flex: 1 }}>
            <option value="">Todas as categorias</option>{(cats.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.name} ({c.count})</option>)}</select>
          <select className="select" value={level} onChange={(e) => setLevel(e.target.value)} style={{ width: 120 }}>
            <option value="">Nível</option><option value="básico">Básico</option><option value="intermédio">Intermédio</option><option value="avançado">Avançado</option></select>
        </div>
        <div className="tiny muted">{terms?.length ?? "…"} termos</div>
        <div style={{ overflowY: "auto" }}>
          {!terms && <Spinner />}
          {grouped.map(([letter, list]) => (
            <div key={letter}>
              <div className="letter">{letter}</div>
              {list.map((t) => (
                <div key={t.id} className={`term-row ${termId === t.id ? "active" : ""}`} onClick={() => nav(`/glossario/${t.id}`)}>
                  <div className="row between"><b className="small">{t.term}</b><Badge tone={LEVEL_TONE[t.level]}>{t.level}</Badge></div>
                  <div className="tiny muted">{t.short}</div>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>
      <div className="card">
        {termId ? <TermDetail id={termId} /> : (
          <div className="stack">
            <h2>Glossário de machine learning para BI</h2>
            <p className="muted">Cada termo tem definição, exemplo em contexto de BI, fórmula quando aplicável, armadilhas, termos relacionados,
              o passo do percurso onde aparece e os hiperparâmetros a que se refere. Os termos aparecem como etiquetas azuis em toda a plataforma.</p>
            <div className="grid auto-sm">
              {(cats.data ?? []).map((c) => (
                <div key={c.id} className="card flat" style={{ cursor: "pointer", padding: 12 }} onClick={() => setCat(c.id)}>
                  <b className="small">{c.name}</b> <span className="tiny muted">({c.count})</span>
                  <div className="tiny muted">{c.description}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function WorkflowTab({ selected }: { selected?: string | null }) {
  const { data } = useFetch<WorkflowStep[]>("/api/knowledge/workflow");
  useEffect(() => { if (selected) document.getElementById(`passo-${selected}`)?.scrollIntoView({ behavior: "smooth" }); }, [selected, data]);
  if (!data) return <Spinner />;
  return (
    <div className="stack">
      <Callout level="info" title="O percurso de um projeto">Os 13 passos que todos os projetos seguem — cada um executado por um agente especializado. Adapte a ordem ao tipo de problema (previsão, segmentação e anomalias saltam alguns passos).</Callout>
      {data.map((s) => (
        <div key={s.id} id={`passo-${s.id}`} className="card" style={selected === s.id ? { borderColor: "var(--primary-2)" } : undefined}>
          <div className="row between"><h3 style={{ margin: 0 }}><span style={{ color: "var(--primary-2)" }}>{s.order}.</span> {s.title}</h3><Badge tone="purple"><Icon name="bot" size={12} />{s.agent_name}</Badge></div>
          <p style={{ marginTop: 6 }}><b>Objetivo:</b> {s.objective}</p>
          <p className="small muted"><b>Porque importa:</b> {s.why}</p>
          <div className="grid cols-3 small">
            <div><b>Como fazer</b><ol style={{ paddingLeft: 18, margin: "4px 0" }}>{s.how.map((h) => <li key={h}>{h}</li>)}</ol></div>
            <div><b>Checklist</b>{s.checklist.map((c) => <div key={c}>☐ {c}</div>)}<div style={{ marginTop: 6 }}><b>Resultados</b>{s.outputs.map((o) => <div key={o}>→ {o}</div>)}</div></div>
            <div><b>Erros comuns</b>{s.mistakes.map((m) => <div key={m} style={{ color: "var(--warn)" }}>⚠ {m}</div>)}</div>
          </div>
          <div style={{ marginTop: 8 }}><TermList ids={s.terms} /></div>
        </div>
      ))}
    </div>
  );
}

function GuidesTab({ selected, onSelect }: { selected?: string | null; onSelect: (id: string) => void }) {
  const { data } = useFetch<Guide[]>("/api/knowledge/guides");
  if (!data) return <Spinner />;
  const g = data.find((x) => x.id === selected) ?? data[0];
  return (
    <div className="grid" style={{ gridTemplateColumns: "280px minmax(0, 1fr)", alignItems: "start" }}>
      <div className="stack tight">
        {data.map((x) => (
          <div key={x.id} className={`term-row ${g?.id === x.id ? "active" : ""}`} onClick={() => onSelect(x.id)}>
            <b className="small">{x.title}</b><div className="tiny muted">{x.audience} · {x.duration}</div>
          </div>
        ))}
      </div>
      {g && (
        <div className="card stack">
          <div><h2>{g.title}</h2><div className="row"><Badge>{g.audience}</Badge><Badge tone="info">{g.duration}</Badge></div><p className="muted" style={{ marginTop: 8 }}>{g.summary}</p></div>
          {g.sections.map((s) => (
            <div key={s.title} className="card flat">
              <h3>{s.title}</h3>
              <Markdown text={s.content} />
              <div style={{ marginTop: 6 }}><TermList ids={s.terms} /></div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function FaqTab() {
  const { data } = useFetch<{ q: string; a: string; terms: string[] }[]>("/api/knowledge/faq");
  const [open, setOpen] = useState<number | null>(0);
  if (!data) return <Spinner />;
  return (
    <div className="stack tight">
      {data.map((f, i) => (
        <div key={i} className="card" style={{ padding: 12 }}>
          <div className="row between" style={{ cursor: "pointer" }} onClick={() => setOpen(open === i ? null : i)}>
            <b>{f.q}</b><Icon name={open === i ? "chevron-down" : "chevron-right"} size={16} /></div>
          {open === i && <div style={{ marginTop: 8 }}><Markdown text={f.a} /><div style={{ marginTop: 6 }}>{f.terms.map((t) => <TermChip key={t} id={t} />)}</div></div>}
        </div>
      ))}
    </div>
  );
}

export default function Glossary() {
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") ?? "glossario") as "glossario" | "percurso" | "guias" | "faq";
  const { terms, termsLoaded } = useApp();
  const setTab = (t: string) => setParams({ tab: t });
  return (
    <div className="stack">
      <div className="page-head">
        <div><h1>Glossário & guias</h1><p>Conceitos de ML explicados para a equipa de BI, o percurso guiado de 13 passos, guias por tipo de problema e perguntas frequentes.</p></div>
        {termsLoaded && <Badge tone="blue">{Object.keys(terms).length} termos</Badge>}
      </div>
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "glossario", label: "Glossário" }, { id: "percurso", label: "Percurso em 13 passos" }, { id: "guias", label: "Guias passo-a-passo" }, { id: "faq", label: "Perguntas frequentes" }]} />
      {tab === "glossario" && <GlossaryTab />}
      {tab === "percurso" && <WorkflowTab selected={params.get("passo")} />}
      {tab === "guias" && <GuidesTab selected={params.get("guia")} onSelect={(id) => setParams({ tab: "guias", guia: id })} />}
      {tab === "faq" && <FaqTab />}
      {!termsLoaded && <Empty title="A carregar…" />}
    </div>
  );
}
