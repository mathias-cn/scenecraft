"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";

import { CompletedPack } from "@/components/completed-pack";
import { PipelineTimeline } from "@/components/pipeline-timeline";
import { ReviewCard } from "@/components/review-card";
import { StatusBadge } from "@/components/status-badge";
import { getProject, retryProjectStage } from "@/lib/api";
import { isJobRunning } from "@/lib/pipeline";
import { STAGE_LABEL, formatCreatedAt, isCompletedPack } from "@/lib/project-ui";
import type { ProjectDetail } from "@/lib/types";

const POLL_MS = 5000;

type ProjectDetailViewProps = {
  initial: ProjectDetail;
};

function normalize(project: ProjectDetail): ProjectDetail {
  return {
    ...project,
    scenes: project.scenes ?? [],
    audio_tracks: project.audio_tracks ?? [],
    transcript_segments: project.transcript_segments ?? [],
    thumbnails: project.thumbnails ?? [],
    descriptions: project.descriptions ?? [],
    jobs: project.jobs ?? [],
  };
}

export function ProjectDetailView({ initial }: ProjectDetailViewProps) {
  const [project, setProject] = useState<ProjectDetail>(() => normalize(initial));
  const [pollError, setPollError] = useState<string | null>(null);
  const [retryBusy, setRetryBusy] = useState(false);
  const running = isJobRunning(project.status, project.jobs);
  const packReady = isCompletedPack(project);

  const refresh = useCallback(async () => {
    try {
      const next = await getProject(project.id);
      setProject(normalize(next));
      setPollError(null);
    } catch (err) {
      setPollError(err instanceof Error ? err.message : "Falha ao atualizar");
    }
  }, [project.id]);

  useEffect(() => {
    setProject(normalize(initial));
  }, [initial]);

  useEffect(() => {
    if (!running) return undefined;
    const tick = () => {
      if (document.visibilityState === "hidden") return;
      void refresh();
    };
    const timer = window.setInterval(tick, POLL_MS);
    return () => window.clearInterval(timer);
  }, [running, refresh]);

  async function onRetry() {
    setRetryBusy(true);
    try {
      await retryProjectStage(project.id);
      await refresh();
    } catch (err) {
      setPollError(err instanceof Error ? err.message : "Falha no retry");
    } finally {
      setRetryBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <Link href="/projects" className="label-tech text-white/40 hover:text-brass-400">
        ← Projetos
      </Link>
      <div className="mt-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-medium tracking-tight text-white">{project.title}</h2>
          <p className="mt-1 font-mono text-[11px] text-white/40">
            {STAGE_LABEL[project.current_stage]} · criado {formatCreatedAt(project.created_at)}
            {running ? " · atualizando a cada 5s" : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={project.status} />
          {project.status === "failed" ? (
            <button
              type="button"
              disabled={retryBusy}
              onClick={() => void onRetry()}
              className="rounded-full bg-red-400 px-3 py-1 font-mono text-[10px] font-medium tracking-wide text-ink-950 uppercase disabled:opacity-50"
            >
              Retry estágio
            </button>
          ) : null}
        </div>
      </div>

      <section className="mt-8 rounded-xl border border-white/[0.08] bg-ink-900 px-4 py-5 md:px-6">
        <p className="label-tech mb-4">Pipeline</p>
        <PipelineTimeline currentStage={project.current_stage} status={project.status} />
      </section>

      {pollError ? (
        <p className="mt-4 font-mono text-xs text-red-300">{pollError}</p>
      ) : null}

      {packReady ? (
        <div className="mt-6">
          <CompletedPack project={project} onUpdated={(next) => setProject(normalize(next))} />
        </div>
      ) : project.status === "paused_for_review" ? (
        <div className="mt-6">
          <ReviewCard project={project} onUpdated={(next) => setProject(normalize(next))} />
        </div>
      ) : null}

      {running && !packReady ? (
        <p className="mt-6 rounded-xl border border-white/10 bg-ink-900 px-4 py-3 text-sm text-white/50">
          Job em execução em <span className="font-mono text-brass-400">{STAGE_LABEL[project.current_stage]}</span>
          . A timeline atualiza sozinha.
        </p>
      ) : null}
    </div>
  );
}
