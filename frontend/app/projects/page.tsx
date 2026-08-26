import Link from "next/link";
import { Suspense } from "react";

import { StatusBadge } from "@/components/status-badge";
import { ApiError, listProjects } from "@/lib/api.server";
import { STAGE_LABEL, formatCreatedAt } from "@/lib/project-ui";
import type { Project } from "@/lib/types";

export const dynamic = "force-dynamic";

export default function ProjectsPage() {
  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-white/45">Projetos no pipeline, do ingest ao YouTube.</p>
        <Link
          href="/projects/new"
          className="rounded-md bg-brass-500 px-3 py-2 text-sm font-medium text-ink-950 transition hover:bg-brass-400"
        >
          Novo projeto
        </Link>
      </div>
      <Suspense fallback={<ProjectListFallback />}>
        <ProjectList />
      </Suspense>
    </div>
  );
}

async function ProjectList() {
  let projects: Project[] = [];
  let error: string | null = null;
  try {
    projects = await listProjects();
  } catch (err) {
    error = err instanceof ApiError || err instanceof Error ? err.message : "Falha ao listar projetos";
  }

  if (error) {
    return (
      <p className="rounded-md border border-red-500/30 bg-red-950/40 px-4 py-3 font-mono text-xs text-red-200">
        {error}
      </p>
    );
  }

  if (projects.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-white/10 px-4 py-12 text-center">
        <p className="text-sm text-white/45">Nenhum projeto ainda.</p>
        <Link href="/projects/new" className="mt-3 inline-block text-sm text-brass-400 hover:text-brass-500">
          Criar o primeiro
        </Link>
      </div>
    );
  }

  return (
    <>
      <ul className="space-y-3 md:hidden">
        {projects.map((project) => (
          <li key={project.id}>
            <Link
              href={`/projects/${project.id}`}
              className="block rounded-xl border border-white/[0.08] bg-ink-900 p-4 transition hover:border-brass-500/40"
            >
              <div className="flex items-start justify-between gap-3">
                <h2 className="text-sm font-medium text-white">{project.title}</h2>
                <StatusBadge status={project.status} />
              </div>
              <p className="mt-2 font-mono text-[11px] text-white/45">
                {STAGE_LABEL[project.current_stage]}
              </p>
              <time className="mt-1 block font-mono text-[11px] text-white/35" dateTime={project.created_at}>
                {formatCreatedAt(project.created_at)}
              </time>
            </Link>
          </li>
        ))}
      </ul>

      <div className="hidden overflow-hidden rounded-xl border border-white/[0.08] md:block">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="bg-ink-900 font-mono text-[10px] tracking-[0.14em] text-white/35 uppercase">
            <tr>
              <th className="px-4 py-3 font-medium">Título</th>
              <th className="px-4 py-3 font-medium">Estágio</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Criado</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.06] bg-ink-950">
            {projects.map((project) => (
              <tr key={project.id} className="relative hover:bg-white/[0.03]">
                <td className="px-4 py-3">
                  <Link
                    href={`/projects/${project.id}`}
                    className="font-medium text-white after:absolute after:inset-0 hover:text-brass-400"
                  >
                    {project.title}
                  </Link>
                </td>
                <td className="px-4 py-3 font-mono text-[11px] text-white/55">
                  {STAGE_LABEL[project.current_stage]}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={project.status} />
                </td>
                <td className="px-4 py-3 font-mono text-[11px] text-white/40">
                  <time dateTime={project.created_at}>{formatCreatedAt(project.created_at)}</time>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function ProjectListFallback() {
  return (
    <div className="animate-pulse space-y-3">
      <div className="h-24 rounded-xl bg-white/5 md:hidden" />
      <div className="hidden h-48 rounded-xl bg-white/5 md:block" />
    </div>
  );
}
