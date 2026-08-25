import Link from "next/link";

export default function ProjectNotFound() {
  return (
    <div className="mx-auto max-w-4xl">
      <p className="text-sm text-white/55">Projeto não encontrado.</p>
      <Link href="/projects" className="mt-3 inline-block text-sm text-brass-400 hover:text-brass-500">
        Voltar aos projetos
      </Link>
    </div>
  );
}
