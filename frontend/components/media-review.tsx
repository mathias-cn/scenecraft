"use client";

import { useEffect, useRef, useState } from "react";

import { advanceProject, getProject, regenerateScene } from "@/lib/api";
import { formatDurationMs, formatTimecode } from "@/lib/pipeline";
import type { ProjectDetail, Scene, TranscriptSegment } from "@/lib/types";

const POLL_MS = 3000;

type MediaReviewProps = {
  project: ProjectDetail;
  onUpdated: (project: ProjectDetail) => void;
};

function sceneTranscript(scene: Scene, segments: TranscriptSegment[]): string {
  const byIndex = new Map(segments.map((segment) => [segment.index, segment]));
  const parts = (scene.source_segment_ids ?? [])
    .map((index) => {
      const segment = byIndex.get(index);
      if (!segment) return "";
      return (segment.text_translated || segment.text_original || "").trim();
    })
    .filter(Boolean);
  return parts.join(" ");
}

function isGenerating(scene: Scene): boolean {
  return scene.status === "generating";
}

export function MediaReview({ project, onUpdated }: MediaReviewProps) {
  const [busy, setBusy] = useState(false);
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const onUpdatedRef = useRef(onUpdated);
  onUpdatedRef.current = onUpdated;
  const scenes = [...(project.scenes ?? [])].sort((a, b) => a.index - b.index);
  const generating = scenes.some(isGenerating) || Boolean(regeneratingId);

  useEffect(() => {
    if (!generating) return undefined;
    const tick = () => {
      if (document.visibilityState === "hidden") return;
      void getProject(project.id)
        .then((next) => {
          const still = (next.scenes ?? []).some(isGenerating);
          if (!still) setRegeneratingId(null);
          onUpdatedRef.current(next);
        })
        .catch((err) => {
          setError(err instanceof Error ? err.message : "Falha ao atualizar as cenas");
        });
    };
    const timer = window.setInterval(tick, POLL_MS);
    return () => window.clearInterval(timer);
  }, [generating, project.id]);

  async function onRegenerate(sceneId: string) {
    setRegeneratingId(sceneId);
    setError(null);
    try {
      const next = await regenerateScene(project.id, sceneId);
      onUpdated(next);
    } catch (err) {
      setRegeneratingId(null);
      setError(err instanceof Error ? err.message : "Não foi possível regenerar a cena");
    }
  }

  async function onApprove() {
    setBusy(true);
    setError(null);
    try {
      await advanceProject(project.id, "media_review");
      onUpdated(await getProject(project.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível avançar");
    } finally {
      setBusy(false);
    }
  }

  if (scenes.length === 0) {
    return <p className="text-sm text-white/40">Nenhuma cena gerada ainda.</p>;
  }

  return (
    <div>
      <ul className="grid gap-3 sm:grid-cols-2">
        {scenes.map((scene) => {
          const text = sceneTranscript(scene, project.transcript_segments ?? []);
          const durationMs = Math.max(0, scene.end_ms - scene.start_ms);
          const pending = isGenerating(scene) || regeneratingId === scene.id;
          const src = scene.media_url || null;
          return (
            <li key={scene.id} className="overflow-hidden rounded-lg border border-white/10 bg-ink-950">
              {src && !pending ? (
                scene.media_type === "video" ? (
                  <video src={src} controls className="aspect-video w-full bg-black" />
                ) : (
                  // eslint-disable-next-line @next/next/no-img-element -- URLs do storage são dinâmicas
                  <img src={src} alt="" className="aspect-video w-full object-cover" />
                )
              ) : (
                <div className="flex aspect-video items-center justify-center bg-white/5 font-mono text-[10px] text-white/25">
                  {pending ? "regenerando…" : "sem mídia"}
                </div>
              )}
              <div className="p-3">
                <p className="font-mono text-[10px] text-white/35">
                  #{scene.index} · {formatTimecode(scene.start_ms)}–{formatTimecode(scene.end_ms)} ·{" "}
                  {formatDurationMs(durationMs)}
                </p>
                <p className="mt-1 text-sm text-white/75">{text || scene.visual_prompt}</p>
                <button
                  type="button"
                  disabled={pending || busy}
                  onClick={() => void onRegenerate(scene.id)}
                  className="mt-3 rounded-md border border-white/15 px-3 py-1.5 text-xs text-white/80 transition hover:border-brass-500 hover:text-brass-400 disabled:opacity-50"
                >
                  {pending ? "Regenerando…" : "Regenerar"}
                </button>
              </div>
            </li>
          );
        })}
      </ul>
      {error ? <p className="mt-4 font-mono text-xs text-red-300">{error}</p> : null}
      <button
        type="button"
        disabled={busy || generating}
        onClick={() => void onApprove()}
        className="mt-5 w-full rounded-md bg-brass-500 px-4 py-2.5 text-sm font-medium text-ink-950 transition hover:bg-brass-400 disabled:opacity-50 sm:w-auto"
      >
        {busy ? "Avançando…" : "Aprovar cenas"}
      </button>
    </div>
  );
}
