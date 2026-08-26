"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { formatUsd } from "@/components/cost-bar-chart";
import { getCostBudget } from "@/lib/api";
import type { CostBudget } from "@/lib/types";

export function DailyCostBanner() {
  const [budget, setBudget] = useState<CostBudget | null>(null);

  useEffect(() => {
    let cancelled = false;
    void getCostBudget()
      .then((next) => {
        if (!cancelled) setBudget(next);
      })
      .catch(() => {
        if (!cancelled) setBudget(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!budget || budget.daily_limit_usd == null) {
    return null;
  }

  const limit = formatUsd(budget.daily_limit_usd);
  const today = formatUsd(budget.today_usd);

  if (budget.limit_reached) {
    return (
      <div
        role="alert"
        className="mb-6 rounded-xl border border-amber-500/35 bg-amber-950/40 px-4 py-3"
      >
        <p className="text-sm font-medium text-amber-200">Limite diário de custo atingido</p>
        <p className="mt-1 text-sm text-amber-100/80">
          Gasto de hoje: {today} de {limit} ({budget.timezone}). Novos jobs pagos (LLM, imagens,
          TTS) estão pausados até o próximo dia.
        </p>
        <div className="mt-2 flex gap-3 text-sm">
          <Link href="/costs" className="text-brass-400 hover:text-brass-300">
            Ver custos
          </Link>
          <Link href="/settings" className="text-brass-400 hover:text-brass-300">
            Ajustar teto
          </Link>
        </div>
      </div>
    );
  }

  return (
    <p className="mb-4 font-mono text-[11px] text-white/35">
      Hoje {today} / {limit}
      <Link href="/costs" className="ml-2 text-white/45 hover:text-brass-400">
        custos
      </Link>
      <Link href="/settings" className="ml-2 text-white/45 hover:text-brass-400">
        teto
      </Link>
    </p>
  );
}
