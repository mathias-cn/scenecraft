import type { Metadata } from "next";
import type { ReactNode } from "react";

import { DailyLimitForm } from "@/components/daily-limit-form";
import { ApiError, getCostBudget } from "@/lib/api";
import { getApiBaseUrl } from "@/lib/config";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Configurações",
};

export default async function SettingsPage() {
  const apiUrl = getApiBaseUrl();
  let form: ReactNode = (
    <p className="mt-8 font-mono text-xs text-red-300">Não foi possível carregar o teto diário.</p>
  );
  try {
    const budget = await getCostBudget();
    form = <DailyLimitForm initial={budget} />;
  } catch (err) {
    const message = err instanceof ApiError || err instanceof Error ? err.message : "falha ao consultar";
    form = <p className="mt-8 font-mono text-xs text-red-300">{message}</p>;
  }

  return (
    <div className="mx-auto max-w-2xl">
      <p className="label-tech mb-3">Sistema</p>
      <h2 className="text-xl font-medium tracking-tight text-white">Configurações</h2>
      <p className="mt-2 text-sm leading-relaxed text-white/50">
        Chaves de providers e filas Celery vivem no backend. O teto diário de custo fica no banco e
        pode ser editado aqui, sem redeploy.
      </p>

      <dl className="mt-8 divide-y divide-white/[0.06] rounded-xl border border-white/[0.08] bg-ink-900">
        <div className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <dt className="label-tech">NEXT_PUBLIC_API_URL</dt>
          <dd className="font-mono text-xs text-brass-400 break-all">{apiUrl}</dd>
        </div>
        <div className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <dt className="label-tech">Client</dt>
          <dd className="font-mono text-xs text-white/55">lib/api-client.ts → FastAPI</dd>
        </div>
      </dl>
      {form}
    </div>
  );
}
