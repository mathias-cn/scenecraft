import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { cache } from "react";

import { ProjectDetailView } from "@/components/project-detail-view";
import { ApiError, getProject } from "@/lib/api";

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
  try {
    const project = await loadProject(params.id);
    return <ProjectDetailView initial={project} />;
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) {
      notFound();
    }
    throw err;
  }
}
