import type { Metadata } from "next";
import { Suspense } from "react";

import { LoginForm } from "@/components/login-form";

export const metadata: Metadata = {
  title: "Entrar",
};

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-ink-950 px-4">
      <div className="w-full max-w-sm rounded-xl border border-white/[0.08] bg-ink-900 p-8">
        <p className="font-mono text-[11px] tracking-[0.22em] text-brass-500 uppercase">SceneCraft</p>
        <h1 className="mt-3 text-lg font-medium text-white">Entrar</h1>
        <p className="mt-2 text-sm text-white/45">Acesso restrito ao dono do sistema.</p>
        <Suspense fallback={<div className="mt-8 h-11 rounded-md bg-white/[0.06]" />}>
          <LoginForm />
        </Suspense>
      </div>
    </main>
  );
}
