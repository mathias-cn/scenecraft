import type { AdvanceResult, Project, ProjectCreate, ProjectDetail } from "./types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const isForm = init?.body instanceof FormData;
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      ...(isForm ? {} : { "Content-Type": "application/json" }),
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `HTTP ${response.status}`);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export function listProjects() {
  return request<Project[]>("/api/projects");
}

export function getProject(id: string) {
  return request<ProjectDetail>(`/api/projects/${id}`);
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
    return request<Project>("/api/projects", { method: "POST", body: form });
  }

  return request<Project>("/api/projects", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function advanceProject(id: string, fromStage?: string) {
  return request<AdvanceResult>(`/api/projects/${id}/advance`, {
    method: "POST",
    body: JSON.stringify(fromStage ? { from_stage: fromStage } : {}),
  });
}

export function retryProjectStage(id: string) {
  return request<AdvanceResult>(`/api/projects/${id}/retry-stage`, {
    method: "POST",
  });
}
