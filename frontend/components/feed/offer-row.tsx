"use client";

import { cn, timeAgo } from "@/lib/utils";
import { fmtValue } from "@/lib/types";
import type { Offer } from "@/lib/types";
import { EFFORT_DOT } from "@/lib/colors";
import { ModelTag } from "@/components/ui/model-tag";

interface OfferRowProps {
  offer: Offer;
  isSelected: boolean;
  onSelect: (id: number) => void;
}

/** Compact one-line row for the master-detail list panel. */
export function OfferRow({ offer, isSelected, onSelect }: OfferRowProps) {
  const dotColor = offer.effort ? (EFFORT_DOT[offer.effort] ?? "bg-zinc-500") : "bg-zinc-600";
  const name = offer.name ?? offer.domain ?? "Unknown";
  const value = fmtValue(offer.amount, offer.unit, offer.currency);

  return (
    <button
      type="button"
      onClick={() => onSelect(offer.id)}
      className={cn(
        "w-full text-left px-3 py-2.5 transition-colors",
        isSelected
          ? "bg-zinc-800 border-l-2 border-l-zinc-400"
          : "border-l-2 border-l-transparent hover:bg-zinc-800/60"
      )}
    >
      <div className="flex items-center gap-2 min-w-0">
        {/* Effort color dot */}
        <span className={cn("w-2 h-2 rounded-full shrink-0", dotColor)} />

        {/* Name */}
        <span
          className={cn(
            "flex-1 min-w-0 truncate text-sm font-medium",
            isSelected ? "text-zinc-100" : "text-zinc-300"
          )}
        >
          {name}
        </span>

        {/* Amount */}
        {value && (
          <span className="text-sm font-bold text-emerald-400 tabular-nums shrink-0">
            {value}
          </span>
        )}
      </div>

      {/* Second line: model tags + age */}
      <div className="flex items-center gap-1.5 mt-1 pl-4 min-w-0">
        <div className="flex gap-1 min-w-0 overflow-hidden">
          {offer.models.slice(0, 3).map((m) => (
            <ModelTag key={m} model={m} />
          ))}
          {offer.models.length > 3 && (
            <span className="text-[10px] text-zinc-600">+{offer.models.length - 3}</span>
          )}
        </div>
        <span className="ml-auto text-[10px] text-zinc-600 shrink-0 tabular-nums">
          {offer.first_seen_at ? timeAgo(offer.first_seen_at) : ""}
        </span>
      </div>
    </button>
  );
}
