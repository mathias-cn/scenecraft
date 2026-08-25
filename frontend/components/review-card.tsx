"use client";

import { useState } from "react";

import { AudioStagePanel } from "@/components/audio-stage-panel";
import { ReviewStageBody, reviewTitle } from "@/components/review-stage-body";
import { TranscriptReview } from "@/components/transcript-review";
import { advanceProject, getProject } from "@/lib/api";
import type { ProjectDetail } from "@/lib/types";

type ReviewCardProps = {
  project: ProjectDetail;
  onUpdated: (project: ProjectDetail) => void;
};

export function ReviewCard({ project, onUpdated }: ReviewCardProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isTranscript = project.current_stage === "transcript_review";
  const isSceneReview = project.current_stage === "scene_review";
  const isAudioStage = project.current_stage === "audio_stage";

  async function onApprove() {
    setBusy(true);
    setError(null);
    try {
      await advanceProject(project.id, project.current_stage);
      onUpdated(await getProject(project.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível avançar");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="rounded-xl border border-brass-500/30 bg-ink-900 p-5">
      <p className="label-tech text-brass-500">paused_for_review</p>
      <h3 className="mt-2 text-lg font-medium text-white">{reviewTitle(project.current_stage)}</h3>
      <p className="mt-1 mb-5 text-sm text-white/45">
        {isTranscript
          ? "Edite o original e a tradução se precisar. Ao aprovar, as alterações são salvas e o pipeline segue."
          : isSceneReview
            ? "Revise as cenas. O modelo de imagem já foi definido na criação do projeto."
            : isAudioStage
              ? "Defina o áudio final. Em seguida o Whisper realinha os tempos das cenas."
              : "Confira o resultado deste estágio. Ao aprovar, o pipeline segue para o próximo."}
      </p>
      {isTranscript ? (
        <TranscriptReview
          key={project.transcript_segments.map((segment) => segment.id).join(",")}
          project={project}
          onUpdated={onUpdated}
        />
      ) : isAudioStage ? (
        <AudioStagePanel project={project} onUpdated={onUpdated} />
      ) : (
        <>
          <ReviewStageBody project={project} />
          {error ? (
            <p className="mt-4 font-mono text-xs text-red-300">{error}</p>
          ) : null}
          <button
            type="button"
            disabled={busy}
            onClick={() => void onApprove()}
            className="mt-5 w-full rounded-md bg-brass-500 px-4 py-2.5 text-sm font-medium text-ink-950 transition hover:bg-brass-400 disabled:opacity-50 sm:w-auto"
          >
            {busy ? "Avançando…" : isSceneReview ? "Aprovar cenas e gerar mídia" : "Aprovar e continuar"}
          </button>
        </>
      )}
    </section>
  );
}
