import Link from "next/link";

export default function CharacterNotFound() {
  return (
    <div className="mx-auto max-w-lg py-16 text-center">
      <p className="label-tech">404</p>
      <h2 className="mt-3 text-xl font-medium text-white">Personagem não encontrado</h2>
      <Link href="/characters" className="mt-6 inline-block text-sm text-brass-400 hover:text-brass-500">
        Voltar aos personagens
      </Link>
    </div>
  );
}
