"use client";

import { useEffect, useId, useState } from "react";

import { IconClose, IconSparkles } from "@/components/icons";
import { generateTitles } from "@/lib/api";

const FIELD =
  "mt-2 w-full rounded-md border border-white/10 bg-ink-950 px-3 py-2 font-sans text-sm font-normal tracking-normal text-white normal-case outline-none focus:border-brass-500";

type TitleSuggestDialogProps = {
  currentTitle: string;
  onSelect: (title: string) => void;
};

export function TitleSuggestDialog({ currentTitle, onSelect }: TitleSuggestDialogProps) {
  const titleId = useId();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(currentTitle);
  const [titles, setTitles] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return undefined;
    setDraft(currentTitle);
    setTitles([]);
    setError(null);
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, currentTitle]);

  async function onGenerate() {
    const value = draft.trim();
    if (!value) {
      setError("Escreva um rascunho de título.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await generateTitles(value);
      setTitles(result.titles);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível gerar títulos");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Sugerir títulos com IA"
        className="mt-2 inline-flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-md border border-white/10 text-brass-400 transition hover:border-brass-500 hover:bg-brass-500/10"
      >
        <IconSparkles className="h-4 w-4" />
      </button>
      {open ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <button
            type="button"
            className="absolute inset-0 bg-black/70"
            aria-label="Fechar"
            onClick={() => setOpen(false)}
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            className="relative z-10 w-full max-w-lg rounded-xl border border-white/[0.08] bg-ink-900 p-5 shadow-xl"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="label-tech">IA</p>
                <h3 id={titleId} className="mt-1 text-lg font-medium text-white">
                  Sugerir títulos
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Fechar"
                className="rounded-md p-1 text-white/40 hover:text-white"
              >
                <IconClose className="h-4 w-4" />
              </button>
            </div>
            <label className="label-tech mt-4 block">
              Rascunho
              <input
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                className={FIELD}
                placeholder="Como eu automatizei meu canal"
              />
            </label>
            <button
              type="button"
              disabled={busy || !draft.trim()}
              onClick={() => void onGenerate()}
              className="mt-4 w-full rounded-md bg-brass-500 px-4 py-2.5 text-sm font-medium text-ink-950 transition hover:bg-brass-400 disabled:opacity-50"
            >
              {busy ? "Gerando…" : "Gerar títulos com IA"}
            </button>
            {error ? <p className="mt-3 font-mono text-xs text-red-300">{error}</p> : null}
            {titles.length > 0 ? (
              <div className="mt-4 space-y-2">
                <p className="label-tech">Sugestões</p>
                {titles.map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => {
                      onSelect(item);
                      setOpen(false);
                    }}
                    className="w-full rounded-lg border border-white/10 px-3 py-2.5 text-left text-sm text-white/90 transition hover:border-brass-500 hover:bg-brass-500/10"
                  >
                    {item}
                  </button>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </>
  );
}
