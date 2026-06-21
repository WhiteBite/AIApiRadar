"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowUpRight, ExternalLink, Radio, Star } from "lucide-react";
import { cn, timeAgo, isWithinHours, scorePct } from "@/lib/utils";
import { fmtValue, EFFORT_LABELS, EFFORT_EMOJI } from "@/lib/types";
import type { Offer, Signal, ServiceStatus } from "@/lib/types";
import { fetchService, apiKeys } from "@/lib/api";
import { useSaved } from "@/lib/saved";
import { TypeBadge } from "@/components/ui/type-badge";
import { ModelTag } from "@/components/ui/model-tag";
import { SourceBadge } from "@/components/ui/source-badge";
import { Favicon } from "@/components/ui/favicon";
import { STATUS_DOT, EFFORT_COLORS } from "@/lib/colors";

/** Forum/source names for display */
const SOURCE_LABEL: Record<string, string> = {
  forum_rss: "Форум", nodeseek: "NodeSeek", "linux.do": "linux.do",
  v2ex: "V2EX", reddit: "Reddit", hackernews: "HN", telegram: "Telegram",
  youtube: "YouTube", github: "GitHub", github_lists: "GitHub", github_issues: "GitHub",
  producthunt: "Product Hunt", huggingface: "HuggingFace",
};

const FORUM_SOURCES = new Set([
  "forum_rss", "nodeseek", "linux.do", "v2ex", "reddit",
  "hackernews", "telegram", "youtube",
]);

export interface OfferDetailProps {
  offer: Offer;
  onClose?: () => void;
}

const STATUS_LABELS_RU: Record<ServiceStatus, string> = {
  active: "Активен",
  dead: "Мёртв",
  new: "Новый",
  unknown: "Неизвестно",
};

function valueColor(unit: Offer["unit"]): string {
  if (unit === "credits") return "text-amber-400";
  if (unit === "days" || unit === "months") return "text-blue-400";
  return "text-emerald-400";
}

function isHttp(url: string | null): url is string {
  return !!url && url.startsWith("http");
}

/** Break a claim_steps blob into individual steps. */
function parseClaimSteps(s: string): string[] {
  return s
    .split(/\n|(?=\d+[.)]\s)|●|•|▪/)
    .map((x) => x.replace(/^\s*\d+[.)]\s*/, "").trim())
    .filter((x) => x.length > 2);
}

// ── Small building blocks ───────────────────────────────────────────────────

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <section>
      <h3 className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-zinc-500">
        {title}
        {count !== undefined && (
          <span className="ml-1.5 text-zinc-600 tabular-nums">{count}</span>
        )}
      </h3>
      {children}
    </section>
  );
}

/** One label/value cell in the dense facts grid. */
function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <dt className="text-[11px] uppercase tracking-wide text-zinc-600">{label}</dt>
      <dd className="mt-0.5 text-[13px] text-zinc-200">{children}</dd>
    </div>
  );
}

function Dash() {
  return <span className="text-zinc-600">—</span>;
}

/** Compact source/provenance row. */
function SourceRow({ sig }: { sig: Signal }) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-zinc-800 bg-zinc-950/50 px-2.5 py-1.5">
      <SourceBadge source={sig.source} />
      {sig.channel && (
        <span className="truncate text-xs text-zinc-400">{sig.channel}</span>
      )}
      {sig.observed_at && (
        <span className="shrink-0 text-[11px] text-zinc-600 tabular-nums">
          {timeAgo(sig.observed_at)}
        </span>
      )}
      {isHttp(sig.source_url) && (
        <a
          href={sig.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="ml-auto inline-flex shrink-0 items-center gap-0.5 text-xs text-zinc-400 hover:text-zinc-100"
        >
          оригинал <ArrowUpRight className="h-3 w-3" />
        </a>
      )}
    </div>
  );
}

/** Card showing an original forum/source post with expandable text. */
function OriginalPost({ sig }: { sig: Signal }) {
  const [expanded, setExpanded] = useState(false);
  const text = sig.raw_text ?? "";
  const isLong = text.length > 400;
  const displayed = !expanded && isLong ? text.slice(0, 400) + "…" : text;
  const label = SOURCE_LABEL[sig.source] ?? sig.source;
  const isForumPost = FORUM_SOURCES.has(sig.source);

  return (
    <div className={`rounded-lg border ${isForumPost ? "border-zinc-700/60 bg-zinc-900" : "border-zinc-800 bg-zinc-950/50"} overflow-hidden`}>
      {/* Post header */}
      <div className="flex items-center gap-2 border-b border-zinc-800 px-3 py-2">
        <SourceBadge source={sig.source} />
        <span className="text-[11px] text-zinc-400 font-medium">{label}</span>
        {sig.channel && (
          <span className="text-[11px] text-zinc-500">{sig.channel}</span>
        )}
        {sig.observed_at && (
          <span className="ml-auto text-[11px] text-zinc-600 tabular-nums">
            {timeAgo(sig.observed_at)}
          </span>
        )}
        {isHttp(sig.source_url) && (
          <a
            href={sig.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-1 inline-flex items-center gap-0.5 text-[11px] text-zinc-500 hover:text-zinc-200"
          >
            оригинал <ArrowUpRight className="h-2.5 w-2.5" />
          </a>
        )}
      </div>
      {/* Post body */}
      <div className="px-3 py-2.5">
        <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-zinc-300">
          {displayed}
        </p>
        {isLong && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="mt-2 text-[12px] text-zinc-500 hover:text-zinc-300 underline underline-offset-2"
          >
            {expanded ? "Свернуть" : "Показать полностью"}
          </button>
        )}
      </div>
    </div>
  );
}

export function OfferDetail({ offer, onClose }: OfferDetailProps) {
  const { data: service } = useQuery({
    queryKey: apiKeys.service(offer.service_id),
    queryFn: () => fetchService(offer.service_id),
    staleTime: 60_000,
  });
  const { isSaved, toggle } = useSaved();

  const domain = offer.domain ?? offer.name ?? "Без названия";
  const value = fmtValue(offer.amount, offer.unit, offer.currency);
  const saved = isSaved(offer.id);
  const aliases = service?.aliases ?? [];

  const status = offer.status;
  const statusDot = STATUS_DOT[status] ?? "bg-zinc-500";

  const effort = offer.effort;
  const reliability = offer.reliability ?? service?.reliability ?? null;
  const relPct = reliability !== null ? scorePct(reliability) : null;
  const engine = offer.engine ?? service?.engine ?? null;
  const isNew = isWithinHours(offer.first_seen_at, 24);

  // Sources: dedup by source_url (fall back to source+text for link-less ones),
  // richest text & real links float to the top.
  const allSignals = service?.signals ?? [];
  const seen = new Set<string>();
  const signals = allSignals
    .slice()
    .sort((a, b) => {
      const linkA = isHttp(a.source_url) ? 1 : 0;
      const linkB = isHttp(b.source_url) ? 1 : 0;
      if (linkA !== linkB) return linkB - linkA;
      return (b.raw_text?.length ?? 0) - (a.raw_text?.length ?? 0);
    })
    .filter((s) => {
      const key = s.source_url ?? `${s.source}:${s.raw_text ?? ""}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

  const steps = offer.claim_steps ? parseClaimSteps(offer.claim_steps) : [];
  // Fallback for "Как получить": the most informative source text.
  const richest = allSignals.reduce<Signal | null>((best, s) => {
    if (!s.raw_text) return best;
    if (!best || (s.raw_text.length > (best.raw_text?.length ?? 0))) return s;
    return best;
  }, null);

  const requirements = offer.requirements?.trim();

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/50">
      {/* ── COMPACT HERO ── */}
      <div className="shrink-0 border-b border-zinc-800 bg-zinc-900 px-5 py-4">
        <div className="flex items-start gap-2.5">
          {onClose && (
            <button
              onClick={onClose}
              className="mt-0.5 text-zinc-500 hover:text-zinc-300 md:hidden"
              aria-label="Назад"
            >
              <ArrowLeft className="h-5 w-5" />
            </button>
          )}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <Favicon domain={offer.domain} size={20} className="shrink-0" />
              <h2 className="truncate text-lg font-semibold leading-tight text-zinc-100">
                {domain}
              </h2>
              <TypeBadge type={offer.type} />
            </div>
            <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1">
              {value && (
                <span
                  className={cn(
                    "text-xl font-bold leading-none tabular-nums",
                    valueColor(offer.unit)
                  )}
                >
                  {value}
                </span>
              )}
              <span className="inline-flex items-center gap-1.5 text-xs text-zinc-400">
                <span className={cn("h-1.5 w-1.5 rounded-full", statusDot)} />
                {STATUS_LABELS_RU[status]}
              </span>
              {isNew && (
                <span className="rounded border border-emerald-500/30 bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-300">
                  new
                </span>
              )}
            </div>
            {aliases.length > 0 && (
              <p className="mt-1 truncate text-xs text-zinc-600">
                также: {aliases.join(", ")}
              </p>
            )}
          </div>
        </div>

        {/* CTA row — normal-sized button, not a slab */}
        <div className="mt-3.5 flex flex-wrap items-center gap-2">
          {isHttp(offer.url) && (
            <a
              href={offer.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-md border border-zinc-600 bg-zinc-800 px-3.5 py-1.5 text-sm font-medium text-zinc-100 transition-colors hover:border-zinc-500 hover:bg-zinc-700"
            >
              Открыть →
            </a>
          )}
          <button
            onClick={() => toggle(offer.id)}
            title={saved ? "Убрать из сохранённых" : "Сохранить"}
            className={cn(
              "inline-flex items-center justify-center rounded-md border px-2.5 py-1.5 transition-colors",
              saved
                ? "border-amber-500/40 bg-amber-500/15 text-amber-300"
                : "border-zinc-700 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-100"
            )}
          >
            <Star className={cn("h-4 w-4", saved && "fill-amber-300")} />
          </button>
          {isHttp(offer.source_url) && (
            <a
              href={offer.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-zinc-500 hover:text-zinc-300"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Открыть оригинал
            </a>
          )}
        </div>
      </div>

      {/* ── Scroll content ── */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="max-w-2xl space-y-6 px-5 py-5">
          {/* DESCRIPTION (parsed from the service page) */}
          {offer.description && (
            <p className="text-[13px] leading-relaxed text-zinc-300">
              {offer.description}
            </p>
          )}

          {/* DENSE FACTS GRID */}
          <dl className="grid grid-cols-2 gap-x-4 gap-y-3.5 sm:grid-cols-3">
            <Fact label="Ценность">
              {value ? (
                <span className={cn("font-semibold tabular-nums", valueColor(offer.unit))}>
                  {value}
                </span>
              ) : (
                <Dash />
              )}
            </Fact>

            <Fact label="Усилие">
              {effort ? (
                <span className={cn("inline-flex items-center gap-1.5 font-medium", EFFORT_COLORS[effort])}>
                  <span aria-hidden="true">{EFFORT_EMOJI[effort]}</span>
                  {EFFORT_LABELS[effort]}
                </span>
              ) : (
                <Dash />
              )}
            </Fact>

            <Fact label="Надёжность">
              {relPct !== null ? (
                <div className="flex items-center gap-2">
                  <span className="tabular-nums">{relPct}%</span>
                  <div className="h-1 w-12 overflow-hidden rounded-full bg-zinc-800">
                    <div
                      className={cn(
                        "h-full rounded-full",
                        relPct >= 66 ? "bg-emerald-400" : relPct >= 33 ? "bg-amber-400" : "bg-red-400"
                      )}
                      style={{ width: `${relPct}%` }}
                    />
                  </div>
                </div>
              ) : (
                <Dash />
              )}
            </Fact>

            <Fact label="Нашли">
              {offer.first_seen_at ? (
                <span className="tabular-nums">{timeAgo(offer.first_seen_at)}</span>
              ) : (
                <Dash />
              )}
            </Fact>

            {engine && <Fact label="Движок">{engine}</Fact>}

            <div className="col-span-2 min-w-0 sm:col-span-3">
              <dt className="text-[11px] uppercase tracking-wide text-zinc-600">Модели</dt>
              <dd className="mt-1">
                {offer.models.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {offer.models.map((m) => (
                      <ModelTag key={m} model={m} />
                    ))}
                  </div>
                ) : (
                  <Dash />
                )}
              </dd>
            </div>
          </dl>

          {/* КАК ПОЛУЧИТЬ */}
          <Section title="Как получить">
            {steps.length > 0 ? (
              <ol className="space-y-2">
                {steps.map((step, i) => (
                  <li key={i} className="flex gap-2.5 text-[13px] leading-relaxed text-zinc-200">
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-zinc-800 text-[11px] font-medium tabular-nums text-zinc-400">
                      {i + 1}
                    </span>
                    <span className="min-w-0">{step}</span>
                  </li>
                ))}
              </ol>
            ) : richest?.raw_text ? (
              <OriginalPost sig={richest} />
            ) : (
              <p className="rounded-md border border-dashed border-zinc-800 px-3 py-2.5 text-[13px] text-zinc-500">
                Шаги не извлечены — открой сайт или оригинал источника.
              </p>
            )}
          </Section>

          {/* ТРЕБОВАНИЯ */}
          {(requirements || offer.referral_required) && (
            <Section title="Требования">
              <div className="space-y-2">
                {requirements && (
                  <p className="text-[13px] leading-relaxed text-zinc-300">{requirements}</p>
                )}
                {offer.referral_required && (
                  <span className="inline-flex items-center gap-1.5 rounded-md border border-amber-500/30 bg-amber-500/15 px-2 py-0.5 text-xs font-medium text-amber-300">
                    🔗 нужна реф-ссылка
                  </span>
                )}
              </div>
            </Section>
          )}

          {/* ОТКУДА */}
          <Section title="Откуда" count={signals.length || undefined}>
            {signals.length > 0 ? (
              <div className="space-y-1.5">
                {signals.map((sig, i) => (
                  <SourceRow key={`${sig.source}-${sig.source_url ?? i}`} sig={sig} />
                ))}
              </div>
            ) : (
              <p className="flex items-center gap-2 text-[13px] text-zinc-500">
                <Radio className="h-3.5 w-3.5" /> Источники загружаются…
              </p>
            )}
          </Section>
        </div>
      </div>
    </div>
  );
}

export function OfferDetailEmpty() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-zinc-800 bg-zinc-900/30 p-8 text-center">
      <ArrowLeft className="h-7 w-7 text-zinc-700" />
      <p className="text-sm text-zinc-500">Выбери оффер слева — здесь появятся детали</p>
    </div>
  );
}
