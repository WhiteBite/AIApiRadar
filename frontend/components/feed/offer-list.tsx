"use client";

import { Inbox } from "lucide-react";
import type { Offer } from "@/lib/types";
import { OfferRow } from "./offer-row";

interface OfferListProps {
  offers: Offer[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  isLoading?: boolean;
}

function SkeletonRows() {
  return (
    <div>
      {Array.from({ length: 12 }).map((_, i) => (
        <div key={i} className="px-3 py-2 border-l-2 border-l-transparent animate-pulse">
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-zinc-800 shrink-0" />
            <div className="h-3 bg-zinc-800 rounded flex-1 max-w-[160px]" />
            <div className="h-3 bg-zinc-800 rounded w-10 ml-auto" />
          </div>
          <div className="h-2 bg-zinc-800/60 rounded w-24 mt-1.5 ml-3.5" />
        </div>
      ))}
    </div>
  );
}

export function OfferList({ offers, selectedId, onSelect, isLoading }: OfferListProps) {
  if (isLoading) return <SkeletonRows />;

  if (offers.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20 text-center">
        <Inbox className="w-8 h-8 text-zinc-700 mb-3" />
        <p className="text-sm text-zinc-500">No offers match.</p>
      </div>
    );
  }

  return (
    <div className="divide-y divide-zinc-800/40">
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
