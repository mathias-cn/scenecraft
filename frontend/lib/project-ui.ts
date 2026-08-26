import type { ProjectStage, ProjectStatus } from "./types";

export const STAGE_LABEL: Record<ProjectStage, string> = {
  created: "Criado",
  transcribing: "Transcrição",
  transcript_review: "Review transcrição",
  scene_planning: "Cenas",
  scene_review: "Review cenas",
  generating_media: "Mídia",
  media_review: "Review mídia",
  audio_stage: "Áudio",
  audio_review: "Review áudio",
  rendering: "Render",
  render_review: "Review render",
  thumbnail_stage: "Thumb",
  description_stage: "Descrição",
  completed: "Concluído",
  failed: "Falhou",
};

export type StatusTone =
  | "running"
  | "paused_for_review"
  | "paused_cost_limit"
  | "failed"
  | "done"
  | "pending"
  | "cancelled";

export function statusTone(status: ProjectStatus): StatusTone {
  if (status === "completed") return "done";
  if (status === "paused_for_review") return "paused_for_review";
  if (status === "paused_cost_limit") return "paused_cost_limit";
  if (status === "failed") return "failed";
  if (status === "cancelled") return "cancelled";
  if (status === "running") return "running";
  return "pending";
}

export const STATUS_LABEL: Record<StatusTone, string> = {
  running: "running",
  paused_for_review: "paused_for_review",
  paused_cost_limit: "limite diário",
  failed: "failed",
  done: "done",
  pending: "pending",
  cancelled: "cancelled",
};

export const STATUS_CLASS: Record<StatusTone, string> = {
  running: "bg-sky-500/15 text-sky-300",
  paused_for_review: "bg-brass-500/15 text-brass-400",
  paused_cost_limit: "bg-amber-500/15 text-amber-300",
  failed: "bg-red-500/15 text-red-300",
  done: "bg-emerald-500/15 text-emerald-300",
  pending: "bg-white/10 text-white/55",
  cancelled: "bg-white/5 text-white/35",
};

export function isCompletedPack(project: { current_stage: ProjectStage; status: ProjectStatus }): boolean {
  if (project.status === "completed") return true;
  return project.current_stage === "completed";
}

export function formatCreatedAt(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Sao_Paulo",
  }).format(date);
}
