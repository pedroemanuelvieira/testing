import {
  Area, Bar, BarChart, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine, ResponsiveContainer, Scatter,
  ScatterChart, Tooltip, XAxis, YAxis, ZAxis,
} from "recharts";
import { formatValue } from "../lib/format";
import type { Block } from "../types";

const COLORS = ["var(--chart-1)", "var(--chart-2)", "var(--chart-3)", "var(--chart-4)", "var(--chart-5)", "var(--chart-6)"];
const PALETTE = ["#2563eb", "#f59e0b", "#10b981", "#8b5cf6", "#ef4444", "#06b6d4", "#ec4899", "#84cc16", "#64748b", "#a855f7"];

const LABELS: Record<string, string> = {
  tpr: "Taxa de verdadeiros positivos", aleatorio: "Aleatório", precisao: "Precisão", base: "Taxa base", recall: "Recall",
  f1: "F1", lucro: "Valor líquido (€)", modelo: "Modelo", observado: "Observado", perfeito: "Calibração perfeita",
  real: "Real", previsao: "Previsão", prev: "Previsto", n: "Nº", lift: "Lift", importancia: "Importância", poder: "Poder preditivo",
  informacao_mutua: "Informação mútua", psi: "PSI", silhueta: "Silhueta", inercia: "Inércia", score: "Score", melhor: "Melhor até agora",
  treino: "Treino", atual: "Atual", indice: "Índice", valor: "Valor", frequencia: "Frequência", pct: "%", wape: "WAPE",
  max_psi: "PSI máximo", CV: "Validação cruzada", Teste: "Teste", Treino: "Treino",
};
const label = (k: string) => LABELS[k] ?? k.replace(/_/g, " ");

function tickFmt(fmt?: string) {
  return (v: any) => (typeof v === "number" ? formatValue(v, fmt === "pct" ? "pct" : fmt === "money" ? "money" : "num") : String(v).slice(0, 18));
}

export function ChartBlock({ block, height = 300 }: { block: Block; height?: number }) {
  const data: any[] = block.data ?? [];
  const ys: string[] = block.y ?? [];
  const opt = block.options ?? {};
  const fmt: string | undefined = opt.fmt;
  if (!data.length) return <div className="muted small">Sem dados para o gráfico.</div>;

  if (block.chart === "scatter") {
    const groups: Record<string, any[]> = {};
    for (const d of data) {
      const g = opt.color ? String(d[opt.color]) : "dados";
      (groups[g] ??= []).push(d);
    }
    const xs = data.map((d) => d[block.x]).filter((v) => typeof v === "number");
    const lo = Math.min(...xs), hi = Math.max(...xs);
    return (
      <div className="chart-box" style={{ height }}>
        <ResponsiveContainer>
          <ScatterChart margin={{ top: 8, right: 16, bottom: 8, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            <XAxis type="number" dataKey={block.x} name={label(block.x)} tickFormatter={tickFmt()} stroke="var(--text-3)" fontSize={11} domain={["auto", "auto"]} />
            <YAxis type="number" dataKey={ys[0]} name={label(ys[0])} tickFormatter={tickFmt()} stroke="var(--text-3)" fontSize={11} domain={["auto", "auto"]} />
            <ZAxis range={[18, 18]} />
            <Tooltip formatter={(v: any) => formatValue(v)} contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8 }} />
            {Object.keys(groups).length > 1 && <Legend wrapperStyle={{ fontSize: 12 }} />}
            {Object.entries(groups).map(([g, pts], i) => (
              <Scatter key={g} name={g} data={pts} fill={PALETTE[i % PALETTE.length]} fillOpacity={0.65} />
            ))}
            {opt.diagonal && <ReferenceLine segment={[{ x: lo, y: lo }, { x: hi, y: hi }]} stroke="var(--text-3)" strokeDasharray="4 4" />}
          </ScatterChart>
        </ResponsiveContainer>
      </div>
    );
  }

  if (block.chart === "bar" || block.chart === "histogram") {
    const horizontal = !!opt.horizontal;
    const h = horizontal ? Math.max(height, data.length * 24 + 40) : height;
    return (
      <div className="chart-box" style={{ height: h }}>
        <ResponsiveContainer>
          <BarChart data={data} layout={horizontal ? "vertical" : "horizontal"} margin={{ top: 8, right: 16, bottom: 8, left: horizontal ? 8 : 0 }}
            barCategoryGap={block.chart === "histogram" ? 1 : "15%"}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
            {horizontal ? (
              <>
                <XAxis type="number" tickFormatter={tickFmt(fmt)} stroke="var(--text-3)" fontSize={11} />
                <YAxis type="category" dataKey={block.x} width={170} stroke="var(--text-3)" fontSize={11} tickFormatter={(v) => String(v).replace(/_/g, " ").slice(0, 26)} interval={0} />
              </>
            ) : (
              <>
                <XAxis dataKey={block.x} stroke="var(--text-3)" fontSize={11} tickFormatter={(v) => String(v).replace(/_/g, " ").slice(0, 14)} />
                <YAxis tickFormatter={tickFmt(fmt)} stroke="var(--text-3)" fontSize={11} />
              </>
            )}
            <Tooltip formatter={(v: any, n: any) => [formatValue(v, fmt), label(String(n))]} contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8 }} />
            {ys.length > 1 && <Legend formatter={(v) => label(String(v))} wrapperStyle={{ fontSize: 12 }} />}
            {(opt.thresholds ?? []).map((t: number, i: number) => (
              horizontal ? <ReferenceLine key={i} x={t} stroke={i ? "var(--crit)" : "var(--warn)"} strokeDasharray="4 4" />
                : <ReferenceLine key={i} y={t} stroke={i ? "var(--crit)" : "var(--warn)"} strokeDasharray="4 4" />
            ))}
            {opt.reference_x !== undefined && !horizontal && <ReferenceLine x={opt.reference_x} stroke="var(--crit)" strokeDasharray="4 4" />}
            {ys.map((y, i) => <Bar key={y} dataKey={y} fill={COLORS[i % COLORS.length]} radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]} />)}
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  }

  // linhas (com banda opcional, eixo x numérico e eixo secundário)
  const band: string[] | undefined = opt.band;
  const secondary: string[] = opt.secondary ?? [];
  const rows = band ? data.map((d) => ({ ...d, __band: d[band[0]] !== undefined ? [d[band[0]], d[band[1]]] : undefined })) : data;
  return (
    <div className="chart-box" style={{ height }}>
      <ResponsiveContainer>
        <ComposedChart data={rows} margin={{ top: 8, right: secondary.length ? 4 : 16, bottom: 8, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis dataKey={block.x} type={opt.numeric_x ? "number" : "category"} domain={opt.numeric_x ? ["auto", "auto"] : undefined}
            tickFormatter={opt.numeric_x ? tickFmt() : (v) => String(v).slice(0, 12)} stroke="var(--text-3)" fontSize={11} minTickGap={18} />
          <YAxis yAxisId="l" tickFormatter={tickFmt(fmt)} stroke="var(--text-3)" fontSize={11} domain={["auto", "auto"]} />
          {secondary.length > 0 && <YAxis yAxisId="r" orientation="right" tickFormatter={tickFmt()} stroke="var(--text-3)" fontSize={11} />}
          <Tooltip formatter={(v: any, n: any) => [Array.isArray(v) ? v.map((x) => formatValue(x, fmt)).join(" – ") : formatValue(v, fmt), n === "__band" ? "Intervalo" : label(String(n))]}
            labelFormatter={(l) => (typeof l === "number" ? formatValue(l) : String(l))}
            contentStyle={{ background: "var(--surface)", border: "1px solid var(--border)", borderRadius: 8 }} />
          <Legend formatter={(v) => (v === "__band" ? "Intervalo de previsão" : label(String(v)))} wrapperStyle={{ fontSize: 12 }} />
          {band && <Area yAxisId="l" dataKey="__band" stroke="none" fill="var(--chart-1)" fillOpacity={0.14} isAnimationActive={false} />}
          {(opt.thresholds ?? []).map((t: number, i: number) => <ReferenceLine key={i} yAxisId="l" y={t} stroke={i ? "var(--crit)" : "var(--warn)"} strokeDasharray="4 4" />)}
          {opt.reference_x !== undefined && <ReferenceLine yAxisId="l" x={opt.reference_x} stroke="var(--crit)" strokeDasharray="4 4" label={{ value: "limiar", fontSize: 11, fill: "var(--crit)" }} />}
          {ys.map((y, i) => (
            <Line key={y} yAxisId="l" type="monotone" dataKey={y} stroke={COLORS[i % COLORS.length]} strokeWidth={y === "aleatorio" || y === "perfeito" || y === "base" ? 1.5 : 2.2}
              strokeDasharray={y === "aleatorio" || y === "perfeito" || y === "base" ? "5 5" : undefined} dot={rows.length < 30} connectNulls={false} isAnimationActive={false} />
          ))}
          {secondary.map((y, i) => <Line key={y} yAxisId="r" type="monotone" dataKey={y} stroke={COLORS[(i + ys.length) % COLORS.length]} strokeWidth={2} dot isAnimationActive={false} />)}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

export function Heatmap({ block }: { block: Block }) {
  const xs: string[] = block.x_labels ?? [];
  const ys: string[] = block.y_labels ?? [];
  const vals: (number | null)[][] = block.values ?? [];
  const flat = vals.flat().filter((v): v is number => typeof v === "number");
  const max = Math.max(...flat.map(Math.abs), 1e-9);
  const min = Math.min(...flat);
  const isInt = block.fmt === "0";
  const color = (v: number | null) => {
    if (v === null || v === undefined) return "var(--surface-3)";
    if (block.diverging) {
      const a = Math.min(1, Math.abs(v) / max);
      return v >= 0 ? `rgba(37, 99, 235, ${0.08 + 0.75 * a})` : `rgba(239, 68, 68, ${0.08 + 0.75 * a})`;
    }
    const a = (v - min) / (Math.max(...flat) - min || 1);
    return `rgba(37, 99, 235, ${0.06 + 0.8 * a})`;
  };
  return (
    <div className="heatmap" style={{ gridTemplateColumns: `minmax(90px, auto) repeat(${xs.length}, minmax(44px, 1fr))` }}>
      <div />
      {xs.map((x) => <div key={x} className={`hm-label ${xs.length > 6 ? "hm-col" : ""}`} style={xs.length > 6 ? undefined : { textAlign: "center" }} title={x}>{x.replace(/_/g, " ")}</div>)}
      {ys.map((y, i) => (
        <div key={y} style={{ display: "contents" }}>
          <div className="hm-label" title={y}>{y.replace(/_/g, " ").slice(0, 40)}</div>
          {xs.map((x, j) => {
            const v = vals[i]?.[j];
            const strong = typeof v === "number" && Math.abs(v) / max > 0.55;
            return (
              <div key={x} className="hm-cell" style={{ background: color(v ?? null), color: strong ? "#fff" : "var(--text)" }} title={`${y} × ${x}: ${v ?? "—"}`}>
                {typeof v === "number" ? (isInt ? formatValue(v, "int") : formatValue(v, "num")) : "—"}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
