"use client";

import { useEffect, useId, useState } from "react";

import { IconClose, IconSparkles } from "@/components/icons";
import { generateScript } from "@/lib/api";

const FIELD =
  "mt-2 w-full rounded-md border border-white/10 bg-ink-950 px-3 py-2 font-sans text-sm font-normal tracking-normal text-white normal-case outline-none focus:border-brass-500";

const DEFAULT_MINUTES = 8;

type ScriptSuggestDialogProps = {
  onSelect: (script: string) => void;
};

export function ScriptSuggestDialog({ onSelect }: ScriptSuggestDialogProps) {
  const titleId = useId();
  const [open, setOpen] = useState(false);
  const [topic, setTopic] = useState("");
  const [minutes, setMinutes] = useState(String(DEFAULT_MINUTES));
  const [script, setScript] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return undefined;
    setTopic("");
    setMinutes(String(DEFAULT_MINUTES));
    setScript("");
    setError(null);
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  async function onGenerate() {
    const value = topic.trim();
    if (!value) {
      setError("Escreva um tópico ou tema.");
      return;
    }
    const parsed = Number(minutes);
    const duration = Number.isFinite(parsed) ? Math.min(30, Math.max(1, parsed)) : DEFAULT_MINUTES;
    setBusy(true);
    setError(null);
    try {
      const result = await generateScript(value, duration);
      setScript(result.script);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível gerar o roteiro");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Gerar roteiro com IA"
        className="inline-flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-md border border-white/10 text-brass-400 transition hover:border-brass-500 hover:bg-brass-500/10"
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
            className="relative z-10 flex max-h-[90vh] w-full max-w-lg flex-col overflow-hidden rounded-xl border border-white/[0.08] bg-ink-900 p-5 shadow-xl"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="label-tech">IA</p>
                <h3 id={titleId} className="mt-1 text-lg font-medium text-white">
                  Gerar roteiro
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
              Tópico ou tema
              <input
                value={topic}
                onChange={(event) => setTopic(event.target.value)}
                className={FIELD}
                placeholder="Como a fotossíntese alimenta as plantas"
              />
            </label>
            <label className="label-tech mt-4 block">
              Duração alvo (minutos)
              <input
                type="number"
                min={1}
                max={30}
                step={1}
                value={minutes}
                onChange={(event) => setMinutes(event.target.value)}
                className={FIELD}
              />
            </label>
            <button
              type="button"
              disabled={busy || !topic.trim()}
              onClick={() => void onGenerate()}
              className="mt-4 w-full rounded-md bg-brass-500 px-4 py-2.5 text-sm font-medium text-ink-950 transition hover:bg-brass-400 disabled:opacity-50"
            >
              {busy ? "Gerando…" : "Gerar roteiro com IA"}
            </button>
            {error ? <p className="mt-3 font-mono text-xs text-red-300">{error}</p> : null}
            {script ? (
              <div className="mt-4 min-h-0 flex-1 space-y-3 overflow-y-auto">
                <p className="label-tech">Roteiro gerado</p>
                <p className="whitespace-pre-wrap rounded-lg border border-white/10 bg-ink-950 px-3 py-2.5 text-sm text-white/90">
                  {script}
                </p>
                <button
                  type="button"
                  onClick={() => {
                    onSelect(script);
                    setOpen(false);
                  }}
                  className="w-full rounded-md border border-brass-500 bg-brass-500/10 px-4 py-2.5 text-sm font-medium text-brass-400 transition hover:bg-brass-500/20"
                >
                  Usar este roteiro
                </button>
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </>
  );
}
