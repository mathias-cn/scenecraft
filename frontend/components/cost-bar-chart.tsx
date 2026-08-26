import type { CostPeriod } from "@/lib/types";

type CostBarChartProps = {
  title: string;
  caption: string;
  points: CostPeriod[];
  label: (period: string) => string;
};

function toAmount(value: string | number): number {
  const amount = typeof value === "number" ? value : Number(value);
  return Number.isFinite(amount) ? amount : 0;
}

export function formatUsd(value: string | number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  }).format(toAmount(value));
}

export function CostBarChart({ title, caption, points, label }: CostBarChartProps) {
  const amounts = points.map((point) => toAmount(point.total_usd));
  const peak = Math.max(0, ...amounts);
  const scale = peak > 0 ? peak : 1;

  return (
    <section className="rounded-xl border border-white/[0.08] bg-ink-900 p-5">
      <p className="label-tech text-brass-500">{title}</p>
      <p className="mt-1 mb-5 text-sm text-white/45">{caption}</p>
      <div className="overflow-x-auto">
        <div className="flex h-48 min-w-[28rem] items-end gap-1">
          {points.map((point, index) => {
            const amount = amounts[index] ?? 0;
            const height = Math.max(amount > 0 ? 6 : 0, Math.round((amount / scale) * 100));
            return (
              <div key={point.period} className="flex min-w-0 flex-1 flex-col items-center gap-1">
                <div className="flex h-40 w-full items-end rounded-sm bg-white/[0.04]">
                  <div
                    title={`${label(point.period)} · ${formatUsd(amount)}`}
                    className="w-full rounded-t-sm bg-brass-500/90"
                    style={{ height: `${height}%` }}
                  />
                </div>
                <span className="font-mono text-[9px] leading-none text-white/35">{label(point.period)}</span>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
