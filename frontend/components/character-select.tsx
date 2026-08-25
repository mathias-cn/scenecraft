"use client";

import { useEffect, useState } from "react";

import { listCharacters } from "@/lib/api";
import { characterLabel } from "@/lib/character-ui";
import type { Character } from "@/lib/types";

type CharacterSelectProps = {
  value: string;
  onChange: (character: Character | null) => void;
};

export function CharacterSelect({ value, onChange }: CharacterSelectProps) {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void listCharacters("approved")
      .then((rows) => {
        if (!cancelled) setCharacters(rows);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Não foi possível carregar os personagens");
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div>
      <p className="label-tech">Personagem</p>
      <p className="mt-2 text-sm text-white/45">
        Opcional. Se escolher um, o estilo das cenas fica travado no estilo desse personagem.
      </p>
      <div className="mt-3 max-h-72 space-y-2 overflow-y-auto pr-1">
        <button
          type="button"
          onClick={() => onChange(null)}
          className={`flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left text-sm transition ${
            !value
              ? "border-brass-500 bg-brass-500/10 text-brass-400"
              : "border-white/10 text-white/55 hover:border-white/20"
          }`}
        >
          <span className="flex h-12 w-9 shrink-0 items-center justify-center rounded bg-ink-950 font-mono text-[9px] uppercase">
            —
          </span>
          Nenhum
        </button>
        {characters.map((item) => {
          const active = item.id === value;
          return (
            <button
              key={item.id}
              type="button"
              onClick={() => onChange(item)}
              className={`flex w-full items-center gap-3 rounded-lg border px-3 py-2 text-left transition ${
                active
                  ? "border-brass-500 bg-brass-500/10"
                  : "border-white/10 hover:border-white/20"
              }`}
            >
              {item.base_image_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={item.base_image_url}
                  alt=""
                  className="h-12 w-9 shrink-0 rounded object-cover bg-ink-950"
                />
              ) : (
                <span className="flex h-12 w-9 shrink-0 items-center justify-center rounded bg-ink-950 font-mono text-[9px] text-white/30 uppercase">
                  —
                </span>
              )}
              <span className="min-w-0">
                <span className={`block truncate text-sm ${active ? "text-brass-400" : "text-white"}`}>
                  {characterLabel(item)}
                </span>
                <span className="block font-mono text-[11px] text-white/40">{item.style?.name ?? "—"}</span>
              </span>
            </button>
          );
        })}
      </div>
      {loading ? <span className="mt-2 block font-mono text-[10px] text-white/35">Carregando personagens…</span> : null}
      {error ? <span className="mt-2 block font-mono text-xs text-red-300">{error}</span> : null}
    </div>
  );
}
