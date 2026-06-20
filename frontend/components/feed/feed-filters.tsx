"use client";

import type { OffersFilters } from "@/lib/types";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";

interface FeedFiltersProps {
  filters: OffersFilters;
  onChange: (filters: OffersFilters) => void;
}

const SORT_OPTIONS = [
  { value: "score", label: "Score" },
  { value: "amount", label: "Amount" },
  { value: "newest", label: "Newest" },
];

export function FeedFilters({ filters, onChange }: FeedFiltersProps) {
  function update(patch: Partial<OffersFilters>) {
    onChange({ ...filters, ...patch });
  }

  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-zinc-800 px-6 py-3 bg-zinc-950 sticky top-0 z-10">
      {/* Search */}
      <Input
        placeholder="Search domain, name…"
        value={filters.q}
        onChange={(e) => update({ q: e.target.value })}
        className="w-48"
      />

      {/* Sort */}
      <Select
        value={filters.sort}
        onChange={(v) => update({ sort: v as OffersFilters["sort"] })}
        options={SORT_OPTIONS}
      />

      {/* Min amount */}
      <Input
        type="number"
        placeholder="Min $"
        value={filters.minAmount === "" ? "" : String(filters.minAmount)}
        onChange={(e) =>
          update({
            minAmount: e.target.value === "" ? "" : Number(e.target.value),
          })
        }
        className="w-20"
      />

      {/* Model filter */}
      <Input
        placeholder="Model"
        value={filters.model}
        onChange={(e) => update({ model: e.target.value })}
        className="w-28"
      />

      {/* Checkboxes */}
      <label className="flex items-center gap-1.5 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={filters.activeOnly}
          onChange={(e) => update({ activeOnly: e.target.checked })}
          className="w-3.5 h-3.5 rounded border-zinc-600 bg-zinc-800 accent-emerald-500 cursor-pointer"
        />
        <span className="text-xs text-zinc-400">Active only</span>
      </label>

      <label className="flex items-center gap-1.5 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={filters.noRefOnly}
          onChange={(e) => update({ noRefOnly: e.target.checked })}
          className="w-3.5 h-3.5 rounded border-zinc-600 bg-zinc-800 accent-emerald-500 cursor-pointer"
        />
        <span className="text-xs text-zinc-400">No referral</span>
      </label>
    </div>
  );
}
