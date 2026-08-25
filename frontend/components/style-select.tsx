"use client";

import { useEffect, useState } from "react";

import { listStyles } from "@/lib/api";
import type { Style } from "@/lib/types";

const FIELD =
  "mt-2 w-full rounded-md border border-white/10 bg-ink-950 px-3 py-2 font-sans text-sm font-normal tracking-normal text-white normal-case outline-none focus:border-brass-500";

function matchesStyle(item: Style, token: string | null | undefined): boolean {
  const keep = token?.trim();
  if (!keep) return false;
  return item.slug === keep || item.id === keep;
}

type StyleSelectProps = {
  value: string;
  onChange: (slug: string) => void;
  includeSlug?: string | null;
  label?: string;
  hint?: string;
};

export function StyleSelect({
  value,
  onChange,
  includeSlug,
  label = "Estilo visual",
  hint = "Usado na geração de cenas e personagens.",
}: StyleSelectProps) {
  const [styles, setStyles] = useState<Style[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void (async () => {
      try {
        const active = await listStyles(true);
        let next = active;
        const keep = includeSlug?.trim();
        if (keep && !active.some((item) => matchesStyle(item, keep))) {
          const all = await listStyles();
          const extra = all.find((item) => matchesStyle(item, keep));
          if (extra) next = [...active, extra];
        }
        if (cancelled) return;
        setStyles(next);
        const selected = next.find((item) => matchesStyle(item, value) || matchesStyle(item, keep));
        if (!value && next.length > 0) onChange(next[0].slug);
        else if (selected && selected.slug !== value) onChange(selected.slug);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Não foi possível carregar os estilos");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [includeSlug]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <label className="label-tech block">
      {label}
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={loading || styles.length === 0}
        className={FIELD}
      >
        {styles.map((item) => (
          <option key={item.id} value={item.slug}>
            {item.name}
            {item.active ? "" : " (inativo)"}
          </option>
        ))}
      </select>
      {hint ? <span className="mt-2 block font-mono text-[10px] font-normal tracking-wide text-white/30 normal-case">{hint}</span> : null}
      {loading ? <span className="mt-1 block font-mono text-[10px] text-white/35">Carregando estilos…</span> : null}
      {error ? <span className="mt-1 block font-mono text-xs text-red-300">{error}</span> : null}
    </label>
  );
}
