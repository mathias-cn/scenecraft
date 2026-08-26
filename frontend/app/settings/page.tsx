import type { Metadata } from "next";

import { formatUsd } from "@/components/cost-bar-chart";
import { ApiError, getCostBudget } from "@/lib/api";
import { getApiBaseUrl } from "@/lib/config";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Configurações",
};

export default async function SettingsPage() {
  const apiUrl = getApiBaseUrl();
  let budgetLabel = "não carregado";
  try {
    const budget = await getCostBudget();
    budgetLabel =
      budget.daily_limit_usd == null
        ? "desligado (sem teto)"
        : `${formatUsd(budget.today_usd)} / ${formatUsd(budget.daily_limit_usd)} (${budget.timezone})`;
  } catch (err) {
    budgetLabel = err instanceof ApiError || err instanceof Error ? err.message : "falha ao consultar";
  }

  return (
    <div className="mx-auto max-w-2xl">
      <p className="label-tech mb-3">Sistema</p>
      <h2 className="text-xl font-medium tracking-tight text-white">Configurações</h2>
      <p className="mt-2 text-sm leading-relaxed text-white/50">
        Chaves de providers e filas Celery vivem no backend. O teto diário vem de{" "}
        <span className="font-mono text-[11px] text-white/70">DAILY_COST_LIMIT_USD</span>.
      </p>

      <dl className="mt-8 divide-y divide-white/[0.06] rounded-xl border border-white/[0.08] bg-ink-900">
        <div className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <dt className="label-tech">NEXT_PUBLIC_API_URL</dt>
          <dd className="font-mono text-xs text-brass-400 break-all">{apiUrl}</dd>
        </div>
        <div className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <dt className="label-tech">Teto diário</dt>
          <dd className="font-mono text-xs text-white/55">{budgetLabel}</dd>
        </div>
        <div className="flex flex-col gap-1 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
          <dt className="label-tech">Client</dt>
          <dd className="font-mono text-xs text-white/55">lib/api-client.ts → FastAPI</dd>
        </div>
      </dl>
    </div>
  );
}
