import type { Metadata } from "next";
import Link from "next/link";

import { CostBarChart, formatUsd } from "@/components/cost-bar-chart";
import { ApiError, getCostSeries } from "@/lib/api.server";
import type { CostSeries } from "@/lib/types";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Custos",
};

function dayLabel(period: string): string {
  const day = period.slice(8, 10);
  return day.replace(/^0/, "") || period;
}

function monthLabel(period: string): string {
  const [year, month] = period.split("-");
  if (!year || !month) return period;
  const date = new Date(Date.UTC(Number(year), Number(month) - 1, 1));
  const label = new Intl.DateTimeFormat("pt-BR", { month: "short", timeZone: "UTC" }).format(date);
  return label.replace(".", "");
}

export default async function CostsPage() {
  let series: CostSeries | null = null;
  let error: string | null = null;
  try {
    series = await getCostSeries();
  } catch (err) {
    error = err instanceof ApiError || err instanceof Error ? err.message : "Falha ao carregar custos";
  }

  return (
    <div className="mx-auto max-w-5xl">
      <p className="text-sm text-white/45">
        Gasto estimado com imagens, Whisper, TTS, personagens, títulos e LLM.
      </p>
      {error ? (
        <p className="mt-6 rounded-md border border-red-500/30 bg-red-950/40 px-4 py-3 font-mono text-xs text-red-200">
          {error}
        </p>
      ) : series ? (
        <div className="mt-6 space-y-6">
          <p className="text-sm text-white/70">
            Total acumulado: <span className="font-medium text-brass-400">{formatUsd(series.total_usd)}</span>
            <span className="ml-2 font-mono text-[11px] text-white/35">{series.timezone}</span>
          </p>
          {series.daily_limit_usd != null ? (
            <p
              className={`rounded-xl border px-4 py-3 text-sm ${
                series.limit_reached
                  ? "border-amber-500/35 bg-amber-950/40 text-amber-100"
                  : "border-white/[0.08] bg-ink-900 text-white/70"
              }`}
            >
              Hoje: <span className="font-medium text-white">{formatUsd(series.today_usd)}</span>
              {" / "}
              {formatUsd(series.daily_limit_usd)}
              {series.limit_reached ? " — limite diário atingido; jobs pagos pausados." : ""}{" "}
              <Link href="/settings" className="text-brass-400 hover:text-brass-300">
                Alterar teto
              </Link>
            </p>
          ) : (
            <p className="text-sm text-white/40">
              Sem teto diário. Defina o valor em{" "}
              <Link href="/settings" className="text-brass-400 hover:text-brass-300">
                Configurações
              </Link>
              .
            </p>
          )}
          <CostBarChart
            title="Por dia"
            caption="Últimos 30 dias, no fuso de São Paulo."
            points={series.daily}
            label={dayLabel}
          />
          <CostBarChart
            title="Por mês"
            caption="Últimos 12 meses."
            points={series.monthly}
            label={monthLabel}
          />
        </div>
      ) : null}
    </div>
  );
}
