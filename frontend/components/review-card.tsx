"use client";

import { useState } from "react";

import { ImageModelPicker } from "@/components/image-model-picker";
import { ReviewStageBody, reviewTitle } from "@/components/review-stage-body";
import { StyleSelect } from "@/components/style-select";
import { TranscriptReview } from "@/components/transcript-review";
import { advanceProject, getProject, patchMediaSettings } from "@/lib/api";
import {
  configString,
  imageProviderOf,
  type ImageQuality,
} from "@/lib/project-form";
import type { ProjectDetail } from "@/lib/types";

type ReviewCardProps = {
  project: ProjectDetail;
  onUpdated: (project: ProjectDetail) => void;
};

function initialQuality(project: ProjectDetail): ImageQuality {
  const value = configString(project.automation_config, "image_quality");
  if (value === "low" || value === "medium" || value === "high") return value;
  return "medium";
}

function initialModel(project: ProjectDetail): string {
  const stored = configString(project.automation_config, "image_model");
  if (stored) return stored;
  return imageProviderOf(project.automation_config) === "openai" ? "gpt-image-2" : "";
}

export function ReviewCard({ project, onUpdated }: ReviewCardProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [imageModel, setImageModel] = useState(() => initialModel(project));
  const [imageQuality, setImageQuality] = useState<ImageQuality>(() => initialQuality(project));
  const [sceneStyle, setSceneStyle] = useState(
    () => configString(project.automation_config, "scene_style") ?? "",
  );
  const isTranscript = project.current_stage === "transcript_review";
  const isSceneReview = project.current_stage === "scene_review";

  async function onApprove() {
    setBusy(true);
    setError(null);
    try {
      if (isSceneReview) {
        const payload: { image_model?: string; image_quality?: string; scene_style?: string } = {};
        if (imageModel) payload.image_model = imageModel;
        if (imageProviderOf(project.automation_config) === "openai") {
          payload.image_quality = imageQuality;
        }
        if (sceneStyle) payload.scene_style = sceneStyle;
        if (payload.image_model || payload.image_quality || payload.scene_style) {
          await patchMediaSettings(project.id, payload);
        }
      }
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
            ? "Revise as cenas e escolha o modelo de imagem antes de gerar a mídia."
            : "Confira o resultado deste estágio. Ao aprovar, o pipeline segue para o próximo."}
      </p>
      {isTranscript ? (
        <TranscriptReview
          key={project.transcript_segments.map((segment) => segment.id).join(",")}
          project={project}
          onUpdated={onUpdated}
        />
      ) : (
        <>
          <ReviewStageBody project={project} />
          {isSceneReview ? (
            <>
              <div className="mt-5 rounded-lg border border-white/10 bg-ink-950/50 p-4">
                <StyleSelect
                  value={sceneStyle}
                  onChange={setSceneStyle}
                  includeSlug={configString(project.automation_config, "scene_style")}
                  hint="Somente estilos ativos aparecem na criação; um estilo já salvo no projeto continua visível mesmo inativo."
                />
              </div>
              <ImageModelPicker
                project={project}
                model={imageModel}
                quality={imageQuality}
                onModelChange={setImageModel}
                onQualityChange={setImageQuality}
              />
            </>
          ) : null}
          {error ? (
            <p className="mt-4 font-mono text-xs text-red-300">{error}</p>
          ) : null}
          <button
            type="button"
            disabled={busy || (isSceneReview && !imageModel)}
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
