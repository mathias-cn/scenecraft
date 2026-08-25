import type { Metadata } from "next";
import Link from "next/link";

import { ProjectCreateForm } from "@/components/project-create-form";

export const metadata: Metadata = {
  title: "Novo projeto",
};

export default function NewProjectPage() {
  return (
    <div className="mx-auto max-w-2xl">
      <Link href="/projects" className="label-tech text-white/40 hover:text-brass-400">
        ← Projetos
      </Link>
      <h2 className="mt-3 text-xl font-medium tracking-tight text-white">Novo projeto</h2>
      <p className="mt-2 mb-8 text-sm leading-relaxed text-white/45">
        Escolha a origem, o idioma da transcrição e quais etapas correm sozinhas. Arquivos vão ao
        storage antes do registro no banco.
      </p>
      <ProjectCreateForm />
    </div>
  );
}
