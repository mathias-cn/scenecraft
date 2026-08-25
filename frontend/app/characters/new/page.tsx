import type { Metadata } from "next";
import Link from "next/link";

import { CharacterCreateForm } from "@/components/character-create-form";

export const metadata: Metadata = {
  title: "Novo personagem",
};

export default function NewCharacterPage() {
  return (
    <div className="mx-auto max-w-2xl">
      <Link href="/characters" className="label-tech text-white/40 hover:text-brass-400">
        ← Personagens
      </Link>
      <h2 className="mt-3 text-xl font-medium tracking-tight text-white">Novo personagem</h2>
      <p className="mt-2 mb-8 text-sm leading-relaxed text-white/45">
        Descreva o personagem, escolha o estilo e, se quiser, envie uma foto de referência. A imagem
        base entra em revisão antes do character set.
      </p>
      <CharacterCreateForm />
    </div>
  );
}
