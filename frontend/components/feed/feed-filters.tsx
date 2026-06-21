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
      <Input
        placeholder="Search domain, name…"
        value={filters.q}
        onChange={(e) => update({ q: e.target.value })}
        className="w-48"
      />
      <Select
        value={filters.sort}
        onChange={(v) => update({ sort: v as OffersFilters["sort"] })}
        options={SORT_OPTIONS}
      />
      <Input
        type="number"
        placeholder="Min $"
        value={filters.minAmount === "" ? "" : String(filters.minAmount)}
        onChange={(e) =>
          update({ minAmount: e.target.value === "" ? "" : Number(e.target.value) })
        }
        className="w-20"
      />
      <Input
        placeholder="Model"
        value={filters.model}
        onChange={(e) => update({ model: e.target.value })}
        className="w-28"
      />
    </div>
  );
}
