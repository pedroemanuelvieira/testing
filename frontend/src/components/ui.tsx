import { useEffect, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Icon } from "./Icon";

export function Markdown({ text }: { text: string }) {
  return (
    <div className="md">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={{ a: ({ href, children }) => <a href={href} target={href?.startsWith("http") ? "_blank" : undefined} rel="noreferrer">{children}</a> }}>
        {text}
      </ReactMarkdown>
    </div>
  );
}

export function Badge({ children, tone }: { children: ReactNode; tone?: "blue" | "ok" | "warn" | "crit" | "info" | "purple" }) {
  return <span className={`badge ${tone ?? ""}`}>{children}</span>;
}

const LEVEL_ICON: Record<string, string> = { info: "info", success: "check", warning: "alert", critical: "x-circle" };

export function Callout({ level = "info", title, children }: { level?: string; title?: ReactNode; children?: ReactNode }) {
  return (
    <div className={`callout ${level}`}>
      <Icon name={LEVEL_ICON[level] ?? "info"} className="ic" size={18} />
      <div style={{ minWidth: 0 }}>
        {title && <div style={{ fontWeight: 650 }}>{title}</div>}
        {children && <div className="small" style={{ color: "var(--text-2)" }}>{children}</div>}
      </div>
    </div>
  );
}

export function Progress({ value }: { value: number }) {
  return <div className="progress"><div style={{ width: `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%` }} /></div>;
}

export function Spinner({ size = 16 }: { size?: number }) {
  return <Icon name="loader" size={size} className="spin" />;
}

export function Empty({ icon = "sparkles", title, children }: { icon?: string; title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <Icon name={icon} size={34} />
      <h3 style={{ marginTop: 10 }}>{title}</h3>
      {children && <div className="small">{children}</div>}
    </div>
  );
}

export function Modal({ title, subtitle, onClose, children, footer, size }: {
  title: ReactNode; subtitle?: ReactNode; onClose: () => void; children: ReactNode; footer?: ReactNode; size?: "sm";
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${size ?? ""}`} role="dialog" aria-modal>
        <div className="modal-head">
          <div><h2 style={{ margin: 0 }}>{title}</h2>{subtitle && <div className="muted small">{subtitle}</div>}</div>
          <button className="icon-btn" onClick={onClose} aria-label="Fechar"><Icon name="x" size={18} /></button>
        </div>
        <div className="modal-body">{children}</div>
        {footer && <div className="modal-foot">{footer}</div>}
      </div>
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: ReactNode }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.id} role="tab" className={`tab ${value === t.id ? "active" : ""}`} onClick={() => onChange(t.id)}>{t.label}</button>
      ))}
    </div>
  );
}

export function CodeBlock({ code, language }: { code: string; language?: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="codeblock" data-lang={language}>
      <button className="copy" onClick={() => { navigator.clipboard?.writeText(code).then(() => { setCopied(true); setTimeout(() => setCopied(false), 1500); }).catch(() => undefined); }}>
        {copied ? "Copiado ✓" : "Copiar"}
      </button>
      {code}
    </div>
  );
}

export function Stars({ n, max = 5 }: { n: number; max?: number }) {
  return <span className="stars" title={`${n}/${max}`}>{"★".repeat(n)}<span style={{ opacity: 0.25 }}>{"★".repeat(Math.max(0, max - n))}</span></span>;
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return <Callout level="critical" title="Ocorreu um erro">{error instanceof Error ? error.message : String(error)}</Callout>;
}

export function Section({ title, icon, actions, children }: { title: ReactNode; icon?: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <section className="card">
      <div className="card-title">
        <h3 className="row" style={{ gap: 8 }}>{icon && <Icon name={icon} size={17} />}{title}</h3>
        {actions && <div className="row">{actions}</div>}
      </div>
      {children}
    </section>
  );
}
