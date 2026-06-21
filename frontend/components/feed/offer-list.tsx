"use client";

import { Inbox } from "lucide-react";
import type { Offer, EffortTier } from "@/lib/types";
import { EFFORT_EMOJI, EFFORT_LABELS } from "@/lib/types";
import { OfferRow } from "./offer-row";

interface OfferListProps {
  offers: Offer[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  isLoading?: boolean;
  /** If true, group by effort tier with section headers */
  grouped?: boolean;
}

function SkeletonRow() {
  return (
    <div className="px-3 py-3 animate-pulse">
      <div className="flex items-center gap-2">
        <div className="w-2 h-2 rounded-full bg-zinc-800 shrink-0" />
        <div className="h-3 bg-zinc-800 rounded flex-1" />
        <div className="h-3 bg-zinc-800 rounded w-10 shrink-0" />
      </div>
      <div className="flex gap-1.5 mt-1.5 pl-4">
        <div className="h-4 bg-zinc-800 rounded-md w-12" />
        <div className="h-4 bg-zinc-800 rounded-md w-10" />
      </div>
    </div>
  );
}

interface SectionHeaderProps {
  effort: EffortTier;
  count: number;
}

function SectionHeader({ effort, count }: SectionHeaderProps) {
  const emoji = EFFORT_EMOJI[effort];
  const label = EFFORT_LABELS[effort];
  return (
    <div className="sticky top-0 z-10 px-3 py-1.5 bg-zinc-950/90 backdrop-blur-sm border-b border-zinc-800/50">
      <span className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">
        {emoji} {label}{" "}
        <span className="text-zinc-700 font-normal normal-case tracking-normal">
          ({count})
        </span>
      </span>
    </div>
  );
}

const EFFORT_ORDER: EffortTier[] = ["easy", "medium", "hard"];

export function OfferList({
  offers,
  selectedId,
  onSelect,
  isLoading,
  grouped = false,
}: OfferListProps) {
  if (isLoading) {
    return (
      <div className="divide-y divide-zinc-800/50">
        {Array.from({ length: 8 }).map((_, i) => (
          <SkeletonRow key={i} />
        ))}
      </div>
    );
  }

  if (offers.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-4 text-center">
        <Inbox className="w-8 h-8 text-zinc-700 mb-3" />
        <p className="text-sm text-zinc-500">No offers match.</p>
      </div>
    );
  }

  if (!grouped) {
    return (
      <div className="divide-y divide-zinc-800/30">
        {offers.map((o) => (
          <OfferRow
            key={o.id}
            offer={o}
            isSelected={o.id === selectedId}
            onSelect={onSelect}
          />
        ))}
      </div>
    );
  }

  // Group by effort tier
  const groups: Record<string, Offer[]> = {};
  const nullGroup: Offer[] = [];

  for (const o of offers) {
    if (o.effort) {
      if (!groups[o.effort]) groups[o.effort] = [];
      groups[o.effort].push(o);
    } else {
      nullGroup.push(o);
    }
  }

  return (
    <div>
      {EFFORT_ORDER.filter((e) => groups[e]?.length).map((effort) => (
        <div key={effort}>
          <SectionHeader effort={effort} count={groups[effort].length} />
          <div className="divide-y divide-zinc-800/30">
            {groups[effort].map((o) => (
              <OfferRow
                key={o.id}
                offer={o}
                isSelected={o.id === selectedId}
                onSelect={onSelect}
              />
            ))}
          </div>
        </div>
      ))}
      {nullGroup.length > 0 && (
        <div>
          <div className="sticky top-0 z-10 px-3 py-1.5 bg-zinc-950/90 backdrop-blur-sm border-b border-zinc-800/50">
            <span className="text-xs font-semibold text-zinc-500 uppercase tracking-widest">
              ⚪ Unknown ({nullGroup.length})
            </span>
          </div>
          <div className="divide-y divide-zinc-800/30">
            {nullGroup.map((o) => (
              <OfferRow
                key={o.id}
                offer={o}
                isSelected={o.id === selectedId}
                onSelect={onSelect}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
