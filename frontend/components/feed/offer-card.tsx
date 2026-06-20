"use client";

import { ExternalLink } from "lucide-react";
import { cn, timeAgo, fmtAmount } from "@/lib/utils";
import { STATUS_DOT } from "@/lib/colors";
import type { Offer } from "@/lib/types";
import { ModelTag } from "@/components/ui/model-tag";
import { StatusBadge } from "@/components/ui/status-badge";
import { TypeBadge } from "@/components/ui/type-badge";
import { LeadBadge } from "@/components/ui/lead-badge";
import { ScoreBar } from "@/components/ui/score-bar";

interface OfferCardProps {
  offer: Offer;
  onClick?: () => void;
}

/** Compute lead hours: delta between domain_first_seen and first_seen_at */
function computeLeadHours(offer: Offer): number | null {
  if (!offer.domain_first_seen || !offer.first_seen_at) return null;
  const domainMs = new Date(offer.domain_first_seen).getTime();
  const offerMs = new Date(offer.first_seen_at).getTime();
  const diffHours = (offerMs - domainMs) / 3_600_000;
  // Lead means certstream saw the domain before the offer surfaced elsewhere
  return diffHours > 0 ? diffHours : null;
}

export function OfferCard({ offer, onClick }: OfferCardProps) {
  const dotClass = STATUS_DOT[offer.status] ?? "bg-zinc-500";
  const amount = fmtAmount(offer.amount, offer.currency);
  const title = offer.name ?? offer.domain ?? "Unknown";
  const showDomain = offer.name && offer.domain && offer.name !== offer.domain;
  const claimSteps = offer.claim_steps ?? "";
  const leadHours = computeLeadHours(offer);

  function handleOpenLink(e: React.MouseEvent) {
    e.stopPropagation();
    if (offer.url) window.open(offer.url, "_blank", "noopener,noreferrer");
  }

  return (
    <div
      className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 hover:border-zinc-700 hover:bg-zinc-900/80 transition-all duration-200 cursor-pointer"
      onClick={onClick}
    >
      {/* Top row: status dot + title block + amount + status badge */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5 min-w-0 flex-1">
          <span
            className={cn("mt-1.5 w-2 h-2 rounded-full shrink-0", dotClass)}
          />
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-zinc-100 truncate leading-snug">
              {title}
            </p>
            {showDomain && (
              <p className="text-xs text-zinc-500 truncate">{offer.domain}</p>
            )}
            <div className="mt-1.5">
              <TypeBadge type={offer.type} />
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {amount && (
            <span className="text-2xl font-bold text-emerald-400 tabular-nums leading-none">
              {amount}
            </span>
          )}
          <StatusBadge status={offer.status} />
        </div>
      </div>

      {/* Divider */}
      <div className="border-t border-zinc-800 my-3" />

      {/* Models row */}
      {offer.models.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mb-3">
          {offer.models.slice(0, 6).map((m) => (
            <ModelTag key={m} model={m} />
          ))}
          {offer.models.length > 6 && (
            <span className="text-xs text-zinc-500 self-center">
              +{offer.models.length - 6} more
            </span>
          )}
        </div>
      )}

      {/* Claim steps */}
      {claimSteps && (
        <p className="text-sm text-zinc-400 mb-3 line-clamp-2 leading-relaxed">
          {claimSteps.length > 100
            ? claimSteps.slice(0, 100) + "…"
            : claimSteps}
        </p>
      )}

      {/* Referral warning */}
      {offer.referral_required && (
        <p className="text-xs text-amber-400/80 mb-3">⚠ referral required</p>
      )}

      {/* Found row */}
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-xs text-zinc-500">
            Found {timeAgo(offer.first_seen_at)}
          </span>
          <LeadBadge leadHours={leadHours} />
        </div>
        {offer.url && (
          <button
            onClick={handleOpenLink}
            className="inline-flex items-center gap-1 text-xs text-zinc-400 hover:text-zinc-200 transition-colors shrink-0"
          >
            Open
            <ExternalLink className="w-3 h-3" />
          </button>
        )}
      </div>

      {/* Score bars */}
      <div className="space-y-1.5">
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
    </div>
  );
}
