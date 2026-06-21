"use client";

import { cn, timeAgo } from "@/lib/utils";
import { fmtValue } from "@/lib/types";
import type { Offer } from "@/lib/types";

interface OfferRowProps {
  offer: Offer;
  isSelected: boolean;
  onSelect: (id: number) => void;
}

const SOURCE_SHORT: Record<string, string> = {
  certstream: "CT", forum_rss: "форум", nodeseek: "nodeseek", github: "gh",
  huggingface: "HF", producthunt: "PH", directories: "каталог", coupon: "купон",
  telegram: "TG", youtube: "YT", export: "чат", crtsh: "CT",
};

// Left accent bar by effort (visible at a glance while scanning)
const EFFORT_BORDER: Record<string, string> = {
  easy: "border-l-emerald-500/70",
  medium: "border-l-amber-500/70",
  hard: "border-l-red-500/70",
};

export function OfferRow({ offer, isSelected, onSelect }: OfferRowProps) {
  const domain = offer.domain ?? offer.name ?? "—";
  const value = fmtValue(offer.amount, offer.unit, offer.currency);
  const valueColor =
    offer.unit === "credits" ? "text-amber-400"
      : offer.unit === "days" || offer.unit === "months" ? "text-blue-400"
        : "text-emerald-400";
  const src = offer.source ? (SOURCE_SHORT[offer.source] ?? offer.source) : null;
  const accent = isSelected
    ? "border-l-blue-500"
    : (offer.effort ? EFFORT_BORDER[offer.effort] : "border-l-transparent") ?? "border-l-transparent";

  return (
    <button
      type="button"
      onClick={() => onSelect(offer.id)}
      className={cn(
        "w-full text-left pl-3 pr-3.5 py-2.5 border-l-[3px] transition-colors",
        accent,
        isSelected ? "bg-zinc-800" : "hover:bg-zinc-800/50"
      )}
    >
      {/* line 1: domain + value */}
      <div className="flex items-baseline gap-2 min-w-0">
        <span className={cn(
          "flex-1 min-w-0 truncate text-[15px] font-medium leading-tight",
          isSelected ? "text-white" : "text-zinc-100"
        )}>
          {domain}
        </span>
        {value && (
          <span className={cn("text-[15px] font-bold tabular-nums shrink-0", valueColor)}>
            {value}
          </span>
        )}
      </div>

      {/* line 2: models + source + age */}
      <div className="flex items-center gap-1.5 mt-1 text-xs min-w-0">
        <span className="flex-1 min-w-0 truncate text-zinc-400">
          {offer.models.slice(0, 4).join(" · ")}
          {offer.models.length > 4 && ` +${offer.models.length - 4}`}
        </span>
        <span className="shrink-0 flex items-center gap-1.5 text-zinc-500">
          {src && <span>{src}</span>}
          {src && <span className="text-zinc-700">·</span>}
          <span className="tabular-nums">{offer.first_seen_at ? timeAgo(offer.first_seen_at) : ""}</span>
        </span>
      </div>
    </button>
  );
}
