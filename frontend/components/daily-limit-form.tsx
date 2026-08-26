"use client";

import { FormEvent, useState } from "react";

import { formatUsd } from "@/components/cost-bar-chart";
import { patchCostBudget } from "@/lib/api";
import type { CostBudget } from "@/lib/types";

type DailyLimitFormProps = {
  initial: CostBudget;
};

export function DailyLimitForm({ initial }: DailyLimitFormProps) {
  const [value, setValue] = useState(
    initial.daily_limit_usd == null ? "" : String(initial.daily_limit_usd),
  );
  const [budget, setBudget] = useState(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const trimmed = value.trim();
    const parsed = trimmed === "" ? null : Number(trimmed);
    if (parsed != null && (!Number.isFinite(parsed) || parsed < 0)) {
      setError("Informe um valor em dólares maior ou igual a zero.");
      setBusy(false);
      return;
    }
    try {
      const next = await patchCostBudget(parsed);
      setBudget(next);
      setValue(next.daily_limit_usd == null ? "" : String(next.daily_limit_usd));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não foi possível salvar o teto");
    } finally {
      setBusy(false);
    }
  }

  const limitLabel =
    budget.daily_limit_usd == null
      ? "desligado (sem teto)"
      : `${formatUsd(budget.today_usd)} / ${formatUsd(budget.daily_limit_usd)} (${budget.timezone})`;

  return (
    <form onSubmit={onSubmit} className="mt-8 space-y-4">
      <p className="font-mono text-xs text-white/55">Uso de hoje: {limitLabel}</p>
      <label className="label-tech block">
        Teto diário (USD)
        <input
          type="number"
          min="0"
          step="0.01"
          value={value}
          onChange={(event) => setValue(event.target.value)}
          placeholder="vazio = sem limite"
          className="mt-2 w-full rounded-md border border-white/10 bg-ink-950 px-3 py-2 font-sans text-sm font-normal tracking-normal text-white normal-case outline-none focus:border-brass-500"
        />
      </label>
      <p className="text-xs leading-relaxed text-white/40">
        Salvo no banco. Deixe em branco para desligar o teto sem redeploy. Jobs pagos pausam quando
        o gasto do dia (fuso de São Paulo) atinge o valor.
      </p>
      {error ? <p className="font-mono text-xs text-red-300">{error}</p> : null}
      <button
        type="submit"
        disabled={busy}
        className="rounded-md bg-brass-500 px-4 py-2 text-sm font-medium text-ink-950 disabled:opacity-50"
      >
        {busy ? "Salvando…" : "Salvar teto"}
      </button>
    </form>
  );
}
