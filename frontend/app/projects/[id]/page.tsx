import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";

import { ProjectActions } from "@/components/project-actions";
import { StatusBadge } from "@/components/status-badge";
import { ApiError, getProject } from "@/lib/api";
import { STAGE_LABEL, formatCreatedAt } from "@/lib/project-ui";

const loadProject = cache(getProject);

type ProjectPageProps = {
  params: { id: string };
};

export async function generateMetadata({ params }: ProjectPageProps): Promise<Metadata> {
  try {
    const project = await loadProject(params.id);
    return { title: project.title };
  } catch {
    return { title: "Projeto" };
  }
}

export const dynamic = "force-dynamic";

export default async function ProjectDetailPage({ params }: ProjectPageProps) {
  let project;
  try {
    project = await loadProject(params.id);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      notFound();
    }
    throw err;
  }

  return (
    <div className="mx-auto max-w-3xl">
      <Link href="/projects" className="label-tech text-white/40 hover:text-brass-400">
        ← Projetos
      </Link>
      <div className="mt-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-xl font-medium tracking-tight text-white">{project.title}</h2>
          <p className="mt-1 font-mono text-[11px] text-white/40">
            {STAGE_LABEL[project.current_stage]} · criado {formatCreatedAt(project.created_at)}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={project.status} />
          <ProjectActions project={project} />
        </div>
      </div>

      <dl className="mt-8 divide-y divide-white/[0.06] rounded-xl border border-white/[0.08] bg-ink-900 text-sm">
        <Row label="source" value={`${project.source_type} · ${project.source_ref}`} />
        <Row label="idioma" value={project.target_language} />
        <Row label="estágio" value={STAGE_LABEL[project.current_stage]} />
      </dl>

      <section className="mt-8">
        <p className="label-tech mb-3">Cenas · áudio · montagem</p>
        <div className="rounded-xl border border-white/[0.08] bg-ink-900 p-4 text-sm text-white/60">
          <p className="font-mono text-[11px]">{project.scenes.length} cena(s)</p>
          <p className="mt-1 font-mono text-[11px]">{project.audio_tracks.length} faixa(s) de áudio</p>
          <p className="mt-1 font-mono text-[11px]">
            Montagem:{" "}
            {project.video_assembly
              ? `${project.video_assembly.status}${
                  project.video_assembly.output_url ? ` · ${project.video_assembly.output_url}` : ""
                }`
              : "ainda não renderizada"}
          </p>
          {project.scenes.slice(0, 8).map((scene) => (
            <p key={scene.id} className="mt-2 text-xs text-white/40">
              #{scene.index} {scene.visual_prompt}
            </p>
          ))}
        </div>
      </section>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-baseline sm:justify-between sm:gap-6">
      <dt className="label-tech shrink-0">{label}</dt>
      <dd className="min-w-0 break-all font-mono text-xs text-white/70">{value}</dd>
    </div>
  );
}
