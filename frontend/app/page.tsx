"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";

import type { FeedTab, OffersFilters, Offer } from "@/lib/types";
import { TAB_FILTERS } from "@/lib/types";
import { fetchOffers, apiKeys } from "@/lib/api";
import type { FetchOffersParams } from "@/lib/api";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { OfferList } from "@/components/feed/offer-list";
import { OfferDetail, OfferDetailEmpty } from "@/components/feed/offer-detail";

// ─── Constants ────────────────────────────────────────────────────────────────

const DEFAULT_FILTERS: OffersFilters = {
  tab: "all",
  q: "",
  minAmount: "",
  model: "",
  sort: "score",
};

const TABS: { value: FeedTab; label: string }[] = [
  { value: "all", label: "All" },
  { value: "easy", label: "🟢 Easy" },
  { value: "medium", label: "🟡 Medium" },
  { value: "hard", label: "🔴 Hard" },
  { value: "dead", label: "💀 Dead" },
];

const SORT_OPTIONS = [
  { value: "score", label: "Score" },
  { value: "amount", label: "Amount" },
  { value: "newest", label: "Newest" },
];

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function FeedPage() {
  const [filters, setFilters] = useState<OffersFilters>(DEFAULT_FILTERS);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  // Build API params
  const tabFilter = TAB_FILTERS[filters.tab];
  const params: FetchOffersParams = {
    limit: 200,
    ...(tabFilter.effort && { effort: tabFilter.effort }),
    ...(tabFilter.status && { status: tabFilter.status }),
    ...(filters.q && { q: filters.q }),
    ...(filters.minAmount !== "" && { min_amount: filters.minAmount }),
    ...(filters.model && { model: filters.model }),
  };

  const { data, isLoading } = useQuery({
    queryKey: apiKeys.offers(params),
    queryFn: () => fetchOffers(params),
    staleTime: 30_000,
  });

  // Client-side sorting
  const offers = useMemo(() => {
    let list = data?.items ?? [];
    if (filters.sort === "newest") {
      list = [...list].sort((a, b) => {
        const ta = a.first_seen_at ? new Date(a.first_seen_at).getTime() : 0;
        const tb = b.first_seen_at ? new Date(b.first_seen_at).getTime() : 0;
        return tb - ta;
      });
    } else if (filters.sort === "amount") {
      list = [...list].sort((a, b) => (b.amount ?? 0) - (a.amount ?? 0));
    }
    return list;
  }, [data, filters.sort]);

  // Selected offer object
  const selectedOffer: Offer | null = useMemo(
    () => offers.find((o) => o.id === selectedId) ?? null,
    [offers, selectedId]
  );

  // Auto-select first item when data loads
  const firstId = offers[0]?.id ?? null;
  if (selectedId === null && firstId !== null) {
    setSelectedId(firstId);
  }

  function handleTabChange(tab: string) {
    setFilters((f) => ({ ...f, tab: tab as FeedTab }));
    setSelectedId(null);
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* ── Top bar: tabs ───────────────────────────────────────────────── */}
      <div className="shrink-0 border-b border-zinc-800 bg-zinc-950">
        <Tabs value={filters.tab} onValueChange={handleTabChange}>
          <TabsList className="rounded-none border-0 bg-transparent px-4 gap-0">
            {TABS.map((t) => (
              <TabsTrigger key={t.value} value={t.value}>
                {t.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      {/* ── Body: list + detail ─────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">

        {/* ── Left: scrollable list panel ────────────────────────────────── */}
        <div className="w-72 xl:w-80 shrink-0 flex flex-col border-r border-zinc-800 overflow-hidden">
          {/* Search + sort bar */}
          <div className="shrink-0 p-2 border-b border-zinc-800 flex gap-2">
            <div className="relative flex-1">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-500 pointer-events-none" />
              <Input
                placeholder="Search…"
                value={filters.q}
                onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))}
                className="pl-8 h-8 text-xs"
              />
            </div>
            <Select
              value={filters.sort}
              onChange={(v) => setFilters((f) => ({ ...f, sort: v as OffersFilters["sort"] }))}
              options={SORT_OPTIONS}
              className="h-8 text-xs w-24 shrink-0"
            />
          </div>

          {/* Count */}
          <div className="shrink-0 px-3 py-1.5 border-b border-zinc-800/50">
            <span className="text-[10px] text-zinc-600 tabular-nums">
              {isLoading ? "Loading…" : `${offers.length} offers`}
            </span>
          </div>

          {/* List */}
          <div className="flex-1 overflow-y-auto">
            <OfferList
              offers={offers}
              selectedId={selectedId}
              onSelect={setSelectedId}
              isLoading={isLoading}
              grouped={filters.tab === "all"}
            />
          </div>
        </div>

        {/* ── Right: detail panel ────────────────────────────────────────── */}
        <div className="flex-1 min-w-0 overflow-hidden p-3">
          {selectedOffer ? (
            <OfferDetail
              offer={selectedOffer}
              onClose={() => setSelectedId(null)}
            />
          ) : (
            <OfferDetailEmpty />
          )}
        </div>
      </div>
    </div>
  );
}
