"use client";

import { ArrowLeft, ExternalLink } from "lucide-react";
import { cn, timeAgo, fmtLead } from "@/lib/utils";
import { fmtValue } from "@/lib/types";
import type { Offer } from "@/lib/types";
import { EffortBadge } from "@/components/ui/effort-badge";
import { TypeBadge } from "@/components/ui/type-badge";
import { StatusBadge } from "@/components/ui/status-badge";
import { ModelTag } from "@/components/ui/model-tag";
import { RequirementIcons } from "@/components/ui/requirement-icons";
import { LeadBadge } from "@/components/ui/lead-badge";
import { ScoreBar } from "@/components/ui/score-bar";

export interface OfferDetailProps {
  offer: Offer;
  onClose?: () => void;
}

/** Delta between domain discovery (certstream) and offer first seen elsewhere. */
function computeLeadHours(offer: Offer): number | null {
  if (!offer.domain_first_seen || !offer.first_seen_at) return null;
  const domainMs = new Date(offer.domain_first_seen).getTime();
  const offerMs = new Date(offer.first_seen_at).getTime();
  const diffHours = (offerMs - domainMs) / 3_600_000;
  return diffHours > 0 ? diffHours : null;
}

/** Split a claim_steps string into individual step strings. */
function parseClaimSteps(claimSteps: string): string[] {
  return claimSteps
    .split(/\n|(?=\d+\.\s)/)
    .map((s) => s.replace(/^\d+\.\s*/, "").trim())
    .filter(Boolean);
}

/** Pick the accent color based on amount unit. */
function getAmountColor(unit: Offer["unit"]): string {
  if (unit === "usd") return "text-emerald-400";
  if (unit === "credits") return "text-amber-400";
  if (unit === "days" || unit === "months") return "text-blue-400";
  return "text-zinc-100";
}

export function OfferDetail({ offer, onClose }: OfferDetailProps) {
  const title = offer.name ?? offer.domain ?? "Unknown";
  const showSubdomain =
    offer.name && offer.domain && offer.name !== offer.domain;
  const amountStr = fmtValue(offer.amount, offer.unit, offer.currency);
  const amountColor = getAmountColor(offer.unit);
  const leadHours = computeLeadHours(offer);
  const leadLabel = fmtLead(leadHours);
  const steps = offer.claim_steps ? parseClaimSteps(offer.claim_steps) : [];

  return (
    <div className="flex flex-col h-full bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
      {/* Mobile back button — hidden on md+ */}
      {onClose && (
        <div className="flex items-center gap-2 px-4 py-3 border-b border-zinc-800 md:hidden">
          <button
            onClick={onClose}
            className="inline-flex items-center gap-1.5 text-sm text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
            Back
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto">
        {/* ── Header ── */}
        <div className="px-4 pt-4 pb-3 border-b border-zinc-800">
          <div className="flex items-start justify-between gap-3">
            <p className="font-semibold text-zinc-100 text-base leading-snug truncate flex-1 min-w-0">
              {title}
            </p>
            <div className="flex items-center gap-1.5 shrink-0">
              <EffortBadge effort={offer.effort} variant="pill" />
              <TypeBadge type={offer.type} />
            </div>
          </div>
          {showSubdomain && (
            <p className="mt-0.5 text-xs text-zinc-500 truncate">
              {offer.domain}
            </p>
          )}
        </div>

        {/* ── Amount ── */}
        {amountStr && (
          <div className="px-4 pt-4 pb-3 border-b border-zinc-800">
            <p className="text-[11px] text-zinc-500 uppercase tracking-widest mb-2">
              Amount
            </p>
            <p
              className={cn(
                "text-5xl font-bold tabular-nums leading-none",
                amountColor
              )}
            >
              {amountStr}
            </p>
            {offer.models.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-3">
                {offer.models.map((m) => (
                  <ModelTag key={m} model={m} />
                ))}
              </div>
            )}
          </div>
        )}

        {/* ── Requirements ── */}
        <div className="px-4 pt-4 pb-3 border-b border-zinc-800">
          <p className="text-[11px] text-zinc-500 uppercase tracking-widest mb-2">
            Requirements
          </p>
          <RequirementIcons offer={offer} />
        </div>

        {/* ── How to claim ── */}
        <div className="px-4 pt-4 pb-3 border-b border-zinc-800">
          <p className="text-[11px] text-zinc-500 uppercase tracking-widest mb-2">
            How to claim
          </p>
          {steps.length > 0 ? (
            <ol className="space-y-2">
              {steps.map((step, i) => (
                <li key={i} className="flex gap-2.5 text-sm text-zinc-300">
                  <span className="text-zinc-500 shrink-0 tabular-nums select-none">
                    {i + 1}.
                  </span>
                  <span>{step}</span>
                </li>
              ))}
            </ol>
          ) : (
            <p className="text-sm text-zinc-500 italic">
              Steps not yet extracted. Check the source.
            </p>
          )}
        </div>

        {/* ── Scores ── */}
        <div className="px-4 pt-4 pb-3 border-b border-zinc-800 space-y-2">
          {offer.reliability !== null && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-zinc-500 w-16 shrink-0">
                Reliability
              </span>
              <ScoreBar score={offer.reliability} className="flex-1" />
            </div>
          )}
          <div className="flex items-center gap-2">
            <span className="text-xs text-zinc-500 w-16 shrink-0">Score</span>
            <ScoreBar score={offer.score} className="flex-1" />
          </div>
        </div>

        {/* ── Footer ── */}
        <div className="px-4 pt-4 pb-5 space-y-3">
          {/* Found time + lead */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-zinc-500">
              Found {timeAgo(offer.first_seen_at)}
            </span>
            {leadLabel && (
              <>
                <span className="text-zinc-700 select-none">·</span>
                <LeadBadge leadHours={leadHours} />
              </>
            )}
          </div>

          {/* Status */}
          <StatusBadge status={offer.status} />

          {/* Open button */}
          {offer.url && (
            <a
              href={offer.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-center gap-2 w-full px-4 py-2.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-100 text-sm font-medium transition-colors"
            >
              Open {offer.domain ?? offer.name ?? "site"} →
              <ExternalLink className="w-4 h-4 shrink-0" />
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

/** Empty state shown when no offer is selected. */
export function OfferDetailEmpty() {
  return (
    <div className="flex flex-col items-center justify-center h-full bg-zinc-900 border border-zinc-800 rounded-xl text-center p-8 gap-3">
      <ArrowLeft className="w-8 h-8 text-zinc-700" />
      <p className="text-zinc-500 text-sm">Select an offer to see details</p>
    </div>
  );
}
