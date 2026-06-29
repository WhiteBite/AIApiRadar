"use client";

import { cn, timeAgo, isWithinHours } from "@/lib/utils";
import { fmtValue } from "@/lib/types";
import type { Offer } from "@/lib/types";
import { Favicon } from "@/components/ui/favicon";
import { LikeButtons } from "@/components/ui/like-buttons";

interface OfferRowProps {
  offer: Offer;
  isSelected: boolean;
  onSelect: (id: number) => void;
}

const SOURCE_SHORT: Record<string, string> = {
  certstream: "CT", forum_rss: "форум", nodeseek: "nodeseek", github: "gh",
  huggingface: "HF", producthunt: "PH", directories: "каталог", coupon: "купон",
  telegram: "TG", youtube: "YT", export: "архив", crtsh: "CT",
  reddit: "reddit", hackernews: "HN", github_lists: "gh",
  github_issues: "gh", github_code: "gh", openrouter: "OR",
  packages: "pkg", leaks: "leak", fofa: "fofa",
};

// Left accent bar by effort (visible at a glance while scanning)
const EFFORT_BORDER: Record<string, string> = {
  easy: "border-l-emerald-500/70",
  medium: "border-l-amber-500/70",
  hard: "border-l-red-500/70",
};

/** Имя для отображения в строке фида.
 *  Если name содержит '/' (hf/deepseek-ai) или короче 3 символов —
 *  это мусор из БД; показываем домен. */
function displayName(offer: Offer): string {
  const n = offer.name;
  if (n && n.length >= 3 && !n.includes("/")) return n;
  return offer.domain ?? offer.name ?? "—";
}

export function OfferRow({ offer, isSelected, onSelect }: OfferRowProps) {
  const domain = displayName(offer);
  const value = fmtValue(offer.amount, offer.unit, offer.currency);
  const valueColor =
    offer.unit === "credits" ? "text-amber-400"
      : offer.unit === "days" || offer.unit === "months" ? "text-blue-400"
        : "text-emerald-400";
  const src = offer.source ? (SOURCE_SHORT[offer.source] ?? offer.source) : null;
  const isNew = isWithinHours(offer.first_seen_at, 24);
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
      {/* line 1: favicon + domain + value */}
      <div className="flex items-center gap-2 min-w-0">
        <Favicon domain={offer.domain} size={14} className="shrink-0 opacity-80" />
        {isNew && (
          <span className="shrink-0 rounded-sm bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 px-1 py-px text-[10px] font-bold uppercase tracking-wide leading-none">
            new
          </span>
        )}
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
      <div className="flex items-center gap-1.5 mt-1 text-[13px] min-w-0 pl-4">
        <span className="flex-1 min-w-0 truncate text-zinc-300">
          {offer.models.length > 0 ? (
            offer.models.slice(0, 4).join(" · ") + (offer.models.length > 4 ? ` +${offer.models.length - 4}` : "")
          ) : (
            <span className="text-zinc-500">—</span>
          )}
        </span>
        <span className="shrink-0 flex items-center gap-1.5 text-zinc-300">
          {src && <span>{src}</span>}
          {src && <span className="text-zinc-500">·</span>}
          <span className="tabular-nums">{offer.first_seen_at ? timeAgo(offer.first_seen_at) : ""}</span>
        </span>
        <LikeButtons offerId={offer.id} compact initialLikes={offer.likes} initialDislikes={offer.dislikes} />
      </div>
    </button>
  );
}
