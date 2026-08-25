import { apiDelete, apiGet, apiPatch, apiPost } from "./api-client";
import type {
  AdvanceResult,
  ImageModelOption,
  Project,
  ProjectCreate,
  ProjectDetail,
  Style,
  TranscriptSegmentPatch,
} from "./types";

export { ApiError } from "./api-client";
export { getApiBaseUrl } from "./config";

export function listProjects() {
  return apiGet<Project[]>("/api/projects");
}

export function getProject(id: string) {
  return apiGet<ProjectDetail>(`/api/projects/${id}`);
}

export function createProject(payload: ProjectCreate, file?: File | null) {
  if (file) {
    const form = new FormData();
    form.append("title", payload.title);
    form.append("source_type", payload.source_type);
    form.append("target_language", payload.target_language);
    form.append("automation_config", JSON.stringify(payload.automation_config ?? {}));
    if (payload.source_ref) form.append("source_ref", payload.source_ref);
    if (payload.image_provider) form.append("image_provider", payload.image_provider);
    form.append("file", file);
    return apiPost<Project>("/api/projects", form);
  }

  return apiPost<Project>("/api/projects", payload);
}

export function advanceProject(id: string, fromStage?: string) {
  return apiPost<AdvanceResult>(
    `/api/projects/${id}/advance`,
    fromStage ? { from_stage: fromStage } : {},
  );
}

export function retryProjectStage(id: string) {
  return apiPost<AdvanceResult>(`/api/projects/${id}/retry-stage`);
}

export function patchTranscript(id: string, segments: TranscriptSegmentPatch[]) {
  return apiPatch<ProjectDetail>(`/api/projects/${id}/transcript`, { segments });
}

export function listImageModels(projectId: string) {
  return apiGet<ImageModelOption[]>(`/api/projects/${projectId}/image-models`);
}

export function patchMediaSettings(
  id: string,
  payload: { image_model?: string; image_quality?: string; scene_style?: string },
) {
  return apiPatch<ProjectDetail>(`/api/projects/${id}/media-settings`, payload);
}

export function listStyles(active?: boolean) {
  const query = active === undefined ? "" : `?active=${active ? "true" : "false"}`;
  return apiGet<Style[]>(`/api/styles${query}`);
}

export function createStyle(payload: { name: string; slug: string }) {
  return apiPost<Style>("/api/styles", payload);
}

export function patchStyle(id: string, active: boolean) {
  return apiPatch<Style>(`/api/styles/${id}`, { active });
}

export function deleteStyle(id: string) {
  return apiDelete<void>(`/api/styles/${id}`);
}
