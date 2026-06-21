"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";

import type { FeedTab, OffersFilters, Offer } from "@/lib/types";
import { TAB_FILTERS } from "@/lib/types";
import { fetchOffers, fetchModels, apiKeys } from "@/lib/api";
import type { FetchOffersParams } from "@/lib/api";

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { OfferList } from "@/components/feed/offer-list";
import { OfferDetail, OfferDetailEmpty } from "@/components/feed/offer-detail";
import { MODEL_COLORS } from "@/lib/colors";
import { useSaved } from "@/lib/saved";

const DEFAULT_FILTERS: OffersFilters = {
  tab: "all", q: "", minAmount: "", model: "", sort: "score",
};

const TABS: { value: FeedTab; label: string }[] = [
  { value: "all", label: "All" },
  { value: "easy", label: "🟢 Easy" },
  { value: "medium", label: "🟡 Medium" },
  { value: "hard", label: "🔴 Hard" },
  { value: "dead", label: "💀 Dead" },
  { value: "saved", label: "⭐" },
];

const SORT_OPTIONS = [
  { value: "score", label: "Top" },
  { value: "amount", label: "Amount" },
  { value: "newest", label: "Newest" },
];

export default function FeedPage() {
  const [filters, setFilters] = useState<OffersFilters>(DEFAULT_FILTERS);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const { ids: savedIds } = useSaved();
  const [liveOnly, setLiveOnly] = useState(false);

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

  const { data: modelsData } = useQuery({
    queryKey: apiKeys.models(),
    queryFn: () => fetchModels(),
    staleTime: 60_000,
  });
  const topModels = (modelsData?.items ?? []).slice(0, 10);

  function toggleModel(m: string) {
    setFilters((f) => ({ ...f, model: f.model === m ? "" : m }));
  }

  const offers = useMemo(() => {
    let list = data?.items ?? [];
    if (filters.tab === "saved") {
      const set = new Set(savedIds);
      list = list.filter((o) => set.has(o.id));
    }
    if (liveOnly) {
      list = list.filter((o) => o.source && o.source !== "export");
    }
    if (filters.sort === "newest") {
      list = [...list].sort((a, b) =>
        (b.first_seen_at ? Date.parse(b.first_seen_at) : 0) -
        (a.first_seen_at ? Date.parse(a.first_seen_at) : 0));
    } else if (filters.sort === "amount") {
      list = [...list].sort((a, b) => (b.amount ?? 0) - (a.amount ?? 0));
    }
    return list;
  }, [data, filters.sort, filters.tab, savedIds, liveOnly]);

  const selectedOffer: Offer | null = useMemo(
    () => offers.find((o) => o.id === selectedId) ?? null,
    [offers, selectedId]
  );

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* ── Toolbar ── */}
      <div className="shrink-0 flex items-center gap-3 px-4 h-12 border-b border-zinc-800 bg-zinc-950">
        <Tabs value={filters.tab} onValueChange={(t) => setFilters((f) => ({ ...f, tab: t as FeedTab }))}>
          <TabsList className="border-0 bg-transparent p-0 gap-1">
            {TABS.map((t) => (
              <TabsTrigger key={t.value} value={t.value}>{t.label}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <div className="flex-1" />

        <button
          onClick={() => setLiveOnly((v) => !v)}
          title="Скрыть сиды из чат-архива — показать только то, что нашли коллекторы"
          className={
            "h-8 px-2.5 rounded-md border text-xs transition-colors shrink-0 " +
            (liveOnly
              ? "border-emerald-500/40 text-emerald-300 bg-emerald-500/10"
              : "border-zinc-700 text-zinc-400 hover:text-zinc-200")
          }
        >
          только живые
        </button>

        <div className="relative w-44">
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
          className="h-8 text-xs w-24"
        />
        <span className="text-[11px] text-zinc-600 tabular-nums w-12 text-right">
          {isLoading ? "…" : offers.length}
        </span>
      </div>

      {/* ── Model filter chips ── */}
      {topModels.length > 0 && (
        <div className="shrink-0 flex items-center gap-1.5 px-4 h-10 border-b border-zinc-800 bg-zinc-950 overflow-x-auto">
          <span className="text-[11px] text-zinc-600 shrink-0 mr-1">Модель:</span>
          {topModels.map(({ model, count }) => {
            const active = filters.model === model;
            const color = MODEL_COLORS[model] ?? "bg-zinc-700/40 text-zinc-300 border-zinc-600";
            return (
              <button
                key={model}
                onClick={() => toggleModel(model)}
                className={`shrink-0 inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-all ${active ? color + " ring-1 ring-white/30" : "border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600"
                  }`}
              >
                {model}
                <span className="text-[10px] opacity-70 tabular-nums">{count}</span>
              </button>
            );
          })}
          {filters.model && (
            <button
              onClick={() => setFilters((f) => ({ ...f, model: "" }))}
              className="shrink-0 text-[11px] text-zinc-500 hover:text-zinc-300 ml-1"
            >
              сбросить
            </button>
          )}
        </div>
      )}

      {/* ── Body: fixed-width list + detail fills rest ── */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        <div className="w-[340px] xl:w-[380px] shrink-0 border-r border-zinc-800 overflow-y-auto">
          <OfferList
            offers={offers}
            selectedId={selectedId}
            onSelect={setSelectedId}
            isLoading={isLoading}
          />
        </div>

        <div className="flex-1 min-w-0 overflow-hidden p-3">
          {selectedOffer ? (
            <OfferDetail offer={selectedOffer} onClose={() => setSelectedId(null)} />
          ) : (
            <OfferDetailEmpty />
          )}
        </div>
      </div>
    </div>
  );
}
