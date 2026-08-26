import { getServerAccessToken } from "@/lib/access-token.server";
import {
  getCharacter as getCharacterRequest,
  getCostBudget as getCostBudgetRequest,
  getCostSeries as getCostSeriesRequest,
  getProject as getProjectRequest,
  listCharacters as listCharactersRequest,
  listProjects as listProjectsRequest,
} from "@/lib/api";
import type { CharacterStatus } from "@/lib/types";

export { ApiError } from "@/lib/api";

async function withAuth(init?: RequestInit): Promise<RequestInit> {
  const token = await getServerAccessToken();
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${token}`);
  return { ...init, headers };
}

export async function listProjects(init?: RequestInit) {
  return listProjectsRequest(await withAuth(init));
}

export async function getProject(id: string, init?: RequestInit) {
  return getProjectRequest(id, await withAuth(init));
}

export async function listCharacters(status?: CharacterStatus, init?: RequestInit) {
  return listCharactersRequest(status, await withAuth(init));
}

export async function getCharacter(id: string, init?: RequestInit) {
  return getCharacterRequest(id, await withAuth(init));
}

export async function getCostSeries(init?: RequestInit) {
  return getCostSeriesRequest(await withAuth(init));
}

export async function getCostBudget(init?: RequestInit) {
  return getCostBudgetRequest(await withAuth(init));
}
