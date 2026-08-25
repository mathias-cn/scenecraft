import { apiGet, apiPost } from "./api-client";
import type { AdvanceResult, Project, ProjectCreate, ProjectDetail } from "./types";

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
