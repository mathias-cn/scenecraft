"use client";

import { useEffect, useRef, useState } from "react";

import { advanceProject, getProject, regenerateRender } from "@/lib/api";
import type { ProjectDetail } from "@/lib/types";

const POLL_MS = 3000;

type RenderReviewProps = {
  project: ProjectDetail;
  onUpdated: (project: ProjectDetail) => void;
};

export function RenderReview({ project, onUpdated }: RenderReviewProps) {
  const [busy, setBusy] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const onUpdatedRef = useRef(onUpdated);
  onUpdatedRef.current = onUpdated;

  const assembly = project.video_assembly;
  const pending = regenerating || assembly?.status === "rendering";
  const failed = assembly?.status === "failed";
  const url = assembly?.output_url ?? null;

  useEffect(() => {
    if (!pending) return undefined;
    const tick = () => {
      if (document.visibilityState === "hidden") return;
      void getProject(project.id)
        .then((next) => {
          const still = next.video_assembly?.status === "rendering";
          if (!still) {
            setRegenerating(false);
          }
          onUpdatedRef.current(next);
        })
        .catch((err) => {
          setError(err instanceof Error ? err.message : "Falha ao atualizar o render");
        });
    };
    const timer = window.setInterval(tick, POLL_MS);
    return () => window.clearInterval(timer);
  }, [pending, project.id]);

  async function onRegenerate() {
    setRegenerating(true);
    setError(null);
    try {
      onUpdated(await regenerateRender(project.id));
    } catch (err) {
      setRegenerating(false);
      setError(err instanceof Error ? err.message : "Não foi possível regenerar o render");
    }
  }

  async function onApprove() {
    setBusy(true);
    setError(null);
    try {
      await advanceProject(project.id, "render_review");
      onUpdated(await getProject(project.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível avançar");
    } finally {
      setBusy(false);
    }
  }

  const src = url || null;

  return (
    <div>
      {src && !pending ? (
        <video controls src={src} className="aspect-video w-full rounded-lg bg-black" />
      ) : (
        <div className="flex aspect-video items-center justify-center rounded-lg bg-white/5 font-mono text-[10px] text-white/25">
          {pending ? "regenerando…" : "Montagem ainda não disponível."}
        </div>
      )}
      {failed ? (
        <p className="mt-3 font-mono text-xs text-red-300">O render falhou. Tente regenerar.</p>
      ) : null}
      {error ? <p className="mt-3 font-mono text-xs text-red-300">{error}</p> : null}
      <div className="mt-5 flex flex-wrap gap-3">
        <button
          type="button"
          disabled={busy || pending}
          onClick={() => void onApprove()}
          className="w-full rounded-md bg-brass-500 px-4 py-2.5 text-sm font-medium text-ink-950 transition hover:bg-brass-400 disabled:opacity-50 sm:w-auto"
        >
          {busy ? "Avançando…" : "Aprovar"}
        </button>
        <button
          type="button"
          disabled={busy || pending}
          onClick={() => void onRegenerate()}
          className="w-full rounded-md border border-white/15 px-4 py-2.5 text-sm text-white/80 transition hover:border-brass-500 hover:text-brass-400 disabled:opacity-50 sm:w-auto"
        >
          {pending ? "Regenerando…" : "Regenerar render"}
        </button>
      </div>
    </div>
  );
}
