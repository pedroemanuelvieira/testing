import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApp } from "../lib/context";
import { Icon } from "./Icon";

/** Etiqueta de um termo do glossário com definição ao passar o rato e ligação para a página do termo. */
export function TermChip({ id, label }: { id: string; label?: string }) {
  const { terms } = useApp();
  const nav = useNavigate();
  const [hover, setHover] = useState(false);
  const t = terms[id];
  if (!t && !label) return null;
  return (
    <button
      className="term-chip"
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      onFocus={() => setHover(true)}
      onBlur={() => setHover(false)}
      onClick={(e) => { e.stopPropagation(); nav(`/glossario/${id}`); }}
      title={t ? undefined : label}
    >
      <Icon name="book-open" size={11} />
      {label ?? t?.term.split(" (")[0]}
      {hover && t && (
        <span className="tooltip" role="tooltip">
          <b>{t.term}</b>
          {t.short}
        </span>
      )}
    </button>
  );
}

export function TermList({ ids, max = 12 }: { ids?: (string | null | undefined)[]; max?: number }) {
  const unique = Array.from(new Set((ids ?? []).filter(Boolean) as string[])).slice(0, max);
  if (!unique.length) return null;
  return <span className="row" style={{ gap: 5 }}>{unique.map((t) => <TermChip key={t} id={t} />)}</span>;
}
