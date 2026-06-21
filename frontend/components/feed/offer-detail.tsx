"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink, Radio, Star } from "lucide-react";
import { cn, timeAgo } from "@/lib/utils";
import { fmtValue } from "@/lib/types";
import type { Offer, Signal } from "@/lib/types";
import { fetchService, apiKeys } from "@/lib/api";
import { EffortBadge } from "@/components/ui/effort-badge";
import { TypeBadge } from "@/components/ui/type-badge";
import { StatusBadge } from "@/components/ui/status-badge";
import { ModelTag } from "@/components/ui/model-tag";
import { RequirementIcons } from "@/components/ui/requirement-icons";
import { LeadBadge } from "@/components/ui/lead-badge";

export interface OfferDetailProps {
  offer: Offer;
  onClose?: () => void;
}

function valueColor(unit: Offer["unit"]): string {
  if (unit === "credits") return "text-amber-400";
  if (unit === "days" || unit === "months") return "text-blue-400";
  return "text-emerald-400";
}

function parseClaimSteps(s: string): string[] {
  return s
    .split(/\n|(?=\d+[.)]\s)|●|•|▪/)
    .map((x) => x.replace(/^\s*\d+[.)]\s*/, "").trim())
    .filter((x) => x.length > 2);
}

function pickProvenance(signals: Signal[]): Signal | null {
  if (!signals.length) return null;
  return [...signals].sort(
    (a, b) => (b.raw_text?.length ?? 0) - (a.raw_text?.length ?? 0)
  )[0];
}

function Section({ title, right, children }: {
  title: string; right?: React.ReactNode; children: React.ReactNode;
}) {
  return (
    <section>
      <div className="flex items-center justify-between mb-2.5">
        <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">
          {title}
        </h3>
        {right}
      </div>
      {children}
    </section>
  );
}

export function OfferDetail({ offer, onClose }: OfferDetailProps) {
  const { data: service } = useQuery({
    queryKey: apiKeys.service(offer.service_id),
    queryFn: () => fetchService(offer.service_id),
    staleTime: 60_000,
  });

  const domain = offer.domain ?? offer.name ?? "Unknown";
  const value = fmtValue(offer.amount, offer.unit, offer.currency);
  const steps = offer.claim_steps ? parseClaimSteps(offer.claim_steps) : [];
  const prov = service ? pickProvenance(service.signals) : null;
  const aliases = service?.aliases ?? [];

  let leadHours: number | null = null;
  if (offer.domain_first_seen && offer.first_seen_at) {
    const d = (Date.parse(offer.first_seen_at) - Date.parse(offer.domain_first_seen)) / 3.6e6;
    leadHours = d > 0 ? d : null;
  }

  return (
    <div className="flex flex-col h-full bg-zinc-900/50 border border-zinc-800 rounded-xl overflow-hidden">
      {/* ── HERO (always visible) ── */}
      <div className="shrink-0 px-6 pt-5 pb-5 border-b border-zinc-800 bg-zinc-900">
        <div className="flex items-start gap-3">
          {onClose && (
            <button onClick={onClose} className="md:hidden mt-1 text-zinc-500 hover:text-zinc-300">
              <ArrowLeft className="w-5 h-5" />
            </button>
          )}
          <h2 className="flex-1 min-w-0 truncate text-2xl font-semibold text-white leading-tight">
            {domain}
          </h2>
          <div className="flex items-center gap-1.5 shrink-0 pt-1">
            <EffortBadge effort={offer.effort} variant="pill" />
            <TypeBadge type={offer.type} />
          </div>
        </div>

        {aliases.length > 0 && (
          <p className="mt-1 text-xs text-zinc-500 truncate">
            также: {aliases.join(", ")}
          </p>
        )}

        <div className="flex items-center gap-3 mt-3 flex-wrap">
          {value && (
            <span className={cn("text-3xl font-bold tabular-nums leading-none", valueColor(offer.unit))}>
              {value}
            </span>
          )}
          <div className="flex flex-wrap gap-1.5">
            {offer.models.map((m) => <ModelTag key={m} model={m} />)}
          </div>
        </div>

        {/* CTA row — always reachable, no scroll needed */}
        <div className="flex items-center gap-2 mt-4">
          {offer.url && (
            <a
              href={offer.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold transition-colors"
            >
              Открыть сайт <ExternalLink className="w-4 h-4" />
            </a>
          )}
          <button
            className="flex items-center justify-center gap-1.5 px-3.5 py-2.5 rounded-lg border border-zinc-700 text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors"
            title="Сохранить (скоро)"
          >
            <Star className="w-4 h-4" />
          </button>
          <div className="ml-1 shrink-0">
            <StatusBadge status={offer.status} />
          </div>
        </div>
      </div>

      {/* ── Scrollable content, constrained reading width ── */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-2xl px-6 py-6 space-y-7">

          {/* Как получить */}
          <Section title="Как получить">
            {steps.length > 0 ? (
              <ol className="space-y-2.5">
                {steps.map((step, i) => (
                  <li key={i} className="flex gap-3 text-[15px] text-zinc-200 leading-relaxed">
                    <span className="flex items-center justify-center shrink-0 w-5 h-5 mt-0.5 rounded-full bg-zinc-800 text-zinc-400 text-xs font-medium tabular-nums">
                      {i + 1}
                    </span>
                    <span className="min-w-0">{step}</span>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-sm text-zinc-500 italic">
                Шаги не извлечены — смотри оригинал поста ниже.
              </p>
            )}
          </Section>

          {/* Откуда */}
          <Section
            title="Откуда"
            right={leadHours ? <LeadBadge leadHours={leadHours} /> : undefined}
          >
            {prov ? (
              <div className="space-y-3">
                <div className="flex items-center gap-2 text-sm text-zinc-400">
                  <Radio className="w-3.5 h-3.5 text-zinc-500 shrink-0" />
                  <span className="font-medium text-zinc-300">{prov.channel ?? prov.source}</span>
                  {prov.observed_at && <span className="text-zinc-500">· {timeAgo(prov.observed_at)}</span>}
                </div>
                {prov.raw_text && (
                  <blockquote className="text-[15px] text-zinc-300 leading-relaxed bg-zinc-950/70 border border-zinc-800 rounded-lg px-4 py-3 whitespace-pre-wrap">
                    {prov.raw_text}
                  </blockquote>
                )}
                {prov.source_url?.startsWith("http") && (
                  <a
                    href={prov.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 text-sm text-blue-400 hover:text-blue-300"
                  >
                    Открыть оригинал <ExternalLink className="w-3.5 h-3.5" />
                  </a>
                )}
              </div>
            ) : (
              <p className="text-sm text-zinc-500 italic">Загрузка источника…</p>
            )}
          </Section>

          {/* Требования */}
          <Section title="Требования">
            <RequirementIcons offer={offer} />
          </Section>
        </div>
      </div>
    </div>
  );
}

export function OfferDetailEmpty() {
  return (
    <div className="flex flex-col items-center justify-center h-full bg-zinc-900/30 border border-dashed border-zinc-800 rounded-xl text-center p-8 gap-3">
      <ArrowLeft className="w-7 h-7 text-zinc-700" />
      <p className="text-sm text-zinc-500">Выбери оффер слева — здесь появятся детали</p>
    </div>
  );
}
