import type { Metadata } from "next";
import Link from "next/link";

import { ProjectCreateForm } from "@/components/project-create-form";

export const metadata: Metadata = {
  title: "Novo projeto",
};

export default function NewProjectPage() {
  return (
    <div className="mx-auto grid max-w-3xl gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)]">
      <div>
        <Link href="/projects" className="label-tech text-white/40 hover:text-brass-400">
          ← Projetos
        </Link>
        <h2 className="mt-3 text-xl font-medium tracking-tight text-white">Novo projeto</h2>
        <p className="mt-2 mb-6 text-sm text-white/45">
          YouTube, upload de vídeo ou áudio. O arquivo vai ao storage antes do registro.
        </p>
        <ProjectCreateForm />
      </div>
      <aside className="self-start rounded-xl border border-dashed border-white/10 p-5 text-sm text-white/50">
        <p className="label-tech">Pipeline</p>
        <ol className="mt-4 space-y-2.5 font-mono text-xs tracking-wide text-white/45">
          <li>01 — ingestão da fonte</li>
          <li>02 — transcrição e tradução</li>
          <li>03 — cenas visuais + áudio</li>
          <li>04 — montagem FFmpeg</li>
          <li>05 — thumb, descrição e YouTube</li>
        </ol>
      </aside>
    </div>
  );
}
