import type { ProjectStage, ProjectStatus } from "./types";

export const PIPELINE_STEPS = [
  {
    id: "transcript",
    label: "Transcript",
    stages: ["created", "transcribing", "transcript_review"],
  },
  {
    id: "scenes",
    label: "Cenas",
    stages: ["scene_planning", "scene_review", "generating_media", "media_review"],
  },
  {
    id: "audio",
    label: "Áudio",
    stages: ["audio_stage", "audio_review"],
  },
  {
    id: "render",
    label: "Render",
    stages: ["rendering", "render_review"],
  },
  {
    id: "thumbnail",
    label: "Thumbnail",
    stages: ["thumbnail_stage"],
  },
  {
    id: "description",
    label: "Descrição",
    stages: ["description_stage"],
  },
  {
    id: "upload",
    label: "Upload",
    stages: ["ready_to_publish", "uploading", "published"],
  },
] as const;

export type PipelineStepId = (typeof PIPELINE_STEPS)[number]["id"];
export type PipelineStepState = "complete" | "current" | "upcoming" | "failed";

export function pipelineStepIndex(stage: ProjectStage): number {
  const index = PIPELINE_STEPS.findIndex((step) =>
    (step.stages as readonly string[]).includes(stage),
  );
  return index;
}

export function pipelineStepState(
  stepIndex: number,
  currentStage: ProjectStage,
  status: ProjectStatus,
): PipelineStepState {
  if (status === "completed" || currentStage === "published") {
    return "complete";
  }
  const current = pipelineStepIndex(currentStage);
  if (current < 0) {
    return status === "failed" ? "failed" : "upcoming";
  }
  if (stepIndex < current) return "complete";
  if (stepIndex === current) {
    return status === "failed" ? "failed" : "current";
  }
  return "upcoming";
}

export function formatTimecode(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
}

export function formatDurationMs(ms: number): string {
  const total = Math.max(0, ms);
  const seconds = total / 1000;
  if (seconds < 60) {
    const rounded = Math.round(seconds * 10) / 10;
    return `${rounded}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const rest = Math.round(seconds % 60);
  return `${minutes}m ${rest}s`;
}

const ACTIVE_JOB_STATUSES = new Set(["queued", "running", "retrying"]);

export function isJobRunning(
  status: ProjectStatus,
  jobs: { status: string }[] = [],
): boolean {
  if (status === "running" || status === "pending") return true;
  return jobs.some((job) => ACTIVE_JOB_STATUSES.has(job.status));
}
