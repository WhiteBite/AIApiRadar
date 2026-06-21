"use client";

import { useQuery } from "@tanstack/react-query";
import { fetchStats, apiKeys } from "@/lib/api";
import { Header } from "@/components/layout/header";
import { TYPE_COLORS, TYPE_LABELS, SOURCE_COLORS } from "@/lib/colors";
import { cn } from "@/lib/utils";

// ─── KPI card ────────────────────────────────────────────────────────────────
function KpiCard({
  label,
  value,
  sub,
  accent,
}: {
  label: string;
  value: string | number;
  sub?: string;
  accent?: string;
}) {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
      <p className="text-xs font-medium text-zinc-500 uppercase tracking-widest mb-1">
        {label}
      </p>
      <p className={cn("text-3xl font-bold tabular-nums", accent ?? "text-zinc-100")}>
        {value}
      </p>
      {sub && <p className="text-xs text-zinc-500 mt-1">{sub}</p>}
    </div>
  );
}

// ─── Type breakdown bar ───────────────────────────────────────────────────────
function TypeBar({ type, count, max }: { type: string; count: number; max: number }) {
  const pct = max > 0 ? Math.round((count / max) * 100) : 0;
  const color = (TYPE_COLORS[type] ?? "bg-zinc-500/15 text-zinc-400 border-zinc-500/30")
    .split(" ")
    .find((c) => c.startsWith("bg-")) ?? "bg-zinc-700";
  const barColor = color.replace("/15", "").replace("bg-", "bg-");
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-zinc-400 w-28 shrink-0 truncate">
        {TYPE_LABELS[type] ?? type}
      </span>
      <div className="flex-1 bg-zinc-800 rounded-full h-2 overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all", barColor)}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-zinc-500 tabular-nums w-6 text-right shrink-0">
        {count}
      </span>
    </div>
  );
}

// ─── Source row ───────────────────────────────────────────────────────────────
const SOURCES = [
  { key: "certstream", label: "CT Logs" },
  { key: "forum_rss", label: "Forum RSS" },
  { key: "github", label: "GitHub" },
  { key: "huggingface", label: "HuggingFace" },
  { key: "producthunt", label: "Product Hunt" },
  { key: "directories", label: "Directories" },
  { key: "coupon", label: "Coupon" },
  { key: "telegram", label: "Telegram" },
  { key: "youtube", label: "YouTube" },
];

function SourceRow({ source }: { source: { key: string; label: string } }) {
  const dot = (SOURCE_COLORS[source.key] ?? "")
    .split(" ")
    .find((c) => c.startsWith("bg-")) ?? "bg-zinc-500";
  return (
    <div className="flex items-center gap-2.5 py-1.5">
      <span className={cn("w-2 h-2 rounded-full shrink-0", dot)} />
      <span className="text-sm text-zinc-300">{source.label}</span>
      <span className="text-xs text-zinc-600 ml-auto">active</span>
    </div>
  );
}

// ─── Page (client component) ──────────────────────────────────────────────────
export default function StatsPage() {
  const { data: stats } = useQuery({
    queryKey: apiKeys.stats(),
    queryFn: () => fetchStats(),
    staleTime: 30_000,
  });

  const byType = stats?.by_type ?? {};
  const maxCount = Math.max(1, ...Object.values(byType).map(Number));
  const deadPct =
    stats && stats.services > 0
      ? Math.round((stats.dead / stats.services) * 100)
      : 0;
  const activePct =
    stats && stats.services > 0
      ? Math.round((stats.active / stats.services) * 100)
      : 0;

  return (
    <div className="min-h-screen bg-zinc-950">
      <Header title="Analytics" subtitle="Monitor coverage and lead times" />

      <div className="px-6 py-6 max-w-5xl space-y-8">
        {/* KPI row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <KpiCard label="Services" value={stats?.services ?? "—"} />
          <KpiCard
            label="Active"
            value={stats?.active ?? "—"}
            sub={`${activePct}% of total`}
            accent="text-emerald-400"
          />
          <KpiCard
            label="Dead"
            value={stats?.dead ?? "—"}
            sub={`${deadPct}% of total`}
            accent="text-red-400"
          />
          <KpiCard label="Offers" value={stats?.offers ?? "—"} />
        </div>

        {/* Type breakdown */}
        <section>
          <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-widest mb-4">
            Offer types
          </h2>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-3">
            {Object.entries(byType).length === 0 ? (
              <p className="text-sm text-zinc-600">No data yet.</p>
            ) : (
              Object.entries(byType)
                .sort((a, b) => Number(b[1]) - Number(a[1]))
                .map(([type, count]) => (
                  <TypeBar
                    key={type}
                    type={type}
                    count={Number(count)}
                    max={maxCount}
                  />
                ))
            )}
          </div>
        </section>

        {/* Sources */}
        <section>
          <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-widest mb-4">
            Active collectors
          </h2>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl px-5 divide-y divide-zinc-800">
            {SOURCES.map((s) => (
              <SourceRow key={s.key} source={s} />
            ))}
          </div>
        </section>

        {/* Lead time placeholder */}
        <section>
          <h2 className="text-sm font-semibold text-zinc-400 uppercase tracking-widest mb-4">
            Lead time vs Telegram
          </h2>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
            <p className="text-sm text-zinc-500">
              Lead time data accumulates as collectors run and Telegram signals
              are ingested. Enable Telegram ingest (
              <code className="text-xs bg-zinc-800 px-1 rounded">
                AIRADAR_TG_API_ID
              </code>
              ) to start measuring.
            </p>
          </div>
        </section>
      </div>
    </div>
  );
}
