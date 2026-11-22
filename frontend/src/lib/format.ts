// Formatação de valores em português de Portugal.

const nf = (opts: Intl.NumberFormatOptions) => new Intl.NumberFormat("pt-PT", opts);
const fmtNum2 = nf({ maximumFractionDigits: 2 });
const fmtNum3 = nf({ maximumFractionDigits: 3 });
const fmtInt = nf({ maximumFractionDigits: 0 });
const fmtPct = nf({ style: "percent", maximumFractionDigits: 1 });
const fmtMoney = nf({ style: "currency", currency: "EUR", maximumFractionDigits: 0 });

export function isNum(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

export function formatValue(v: unknown, fmt?: string): string {
  if (v === null || v === undefined || (typeof v === "number" && !Number.isFinite(v))) return "—";
  switch (fmt) {
    case "pct":
      return isNum(v) ? fmtPct.format(v) : String(v);
    case "int":
      return isNum(v) ? fmtInt.format(v) : String(v);
    case "money":
      return isNum(v) ? fmtMoney.format(v) : String(v);
    case "num":
      return isNum(v) ? (Math.abs(v) >= 100 ? fmtNum2.format(v) : fmtNum3.format(v)) : String(v);
    case "score":
      return isNum(v) ? `${fmtInt.format(v)}/100` : String(v);
    default:
      if (isNum(v)) {
        if (Number.isInteger(v)) return fmtInt.format(v);
        return Math.abs(v) >= 100 ? fmtNum2.format(v) : fmtNum3.format(v);
      }
      if (typeof v === "boolean") return v ? "sim" : "não";
      if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v)) return formatDate(v);
      return String(v);
  }
}

export function formatDate(iso?: string | null, withTime = true): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString("pt-PT", withTime ? { dateStyle: "short", timeStyle: "short" } : { dateStyle: "medium" });
}

export function relativeTime(iso?: string | null): string {
  if (!iso) return "";
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return "agora mesmo";
  if (diff < 3600) return `há ${Math.round(diff / 60)} min`;
  if (diff < 86400) return `há ${Math.round(diff / 3600)} h`;
  return `há ${Math.round(diff / 86400)} dias`;
}

export const PROBLEM_LABEL: Record<string, string> = {
  binary_classification: "Classificação binária",
  multiclass_classification: "Classificação multiclasse",
  regression: "Regressão",
  forecasting: "Previsão temporal",
  clustering: "Segmentação",
  anomaly_detection: "Anomalias",
  association_rules: "Cabaz / associação",
};

export const STATUS_LABEL: Record<string, string> = {
  pending: "Por fazer", done: "Concluído", warning: "Com avisos", error: "Erro", skipped: "Ignorado",
};

export const LEVEL_LABEL: Record<string, string> = { básico: "Básico", intermédio: "Intermédio", avançado: "Avançado" };

export function humanize(col: string): string {
  return col.replace(/_/g, " ");
}

export function metricName(id: string): string {
  const names: Record<string, string> = {
    roc_auc: "AUC-ROC", pr_auc: "PR-AUC", f1: "F1", f1_macro: "F1-macro", f1_weighted: "F1-weighted", precision: "Precisão",
    recall: "Recall", accuracy: "Accuracy", balanced_accuracy: "Balanced acc.", log_loss: "Log loss", brier: "Brier",
    mae: "MAE", rmse: "RMSE", r2: "R²", mape: "MAPE", smape: "sMAPE", wape: "WAPE", mase: "MASE", bias: "Bias",
    silhouette: "Silhueta", davies_bouldin: "Davies-Bouldin", precision_at_k: "Precisão top-k", lift: "Lift", ks: "KS",
    gini: "Gini", lift_top_decile: "Lift 1.º decil", mcc: "MCC", support: "Suporte", confidence: "Confiança",
  };
  return names[id] ?? id;
}

export const PCT_METRICS = new Set(["precision", "recall", "accuracy", "balanced_accuracy", "mape", "smape", "wape", "bias", "precision_at_k", "recall_at_k", "flagged_rate"]);
