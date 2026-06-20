"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Inbox } from "lucide-react";

import type { FeedTab, OffersFilters } from "@/lib/types";
import { TAB_FILTERS } from "@/lib/types";
import { fetchOffers, apiKeys } from "@/lib/api";
import type { FetchOffersParams } from "@/lib/api";

import { Header } from "@/components/layout/header";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FeedFilters } from "@/components/feed/feed-filters";
import { OfferCard } from "@/components/feed/offer-card";

// ─── Default filters ──────────────────────────────────────────────────────────

const DEFAULT_FILTERS: OffersFilters = {
  tab: "all",
  q: "",
  minAmount: "",
  model: "",
  activeOnly: false,
  noRefOnly: false,
  sort: "score",
};

// ─── Loading skeletons ────────────────────────────────────────────────────────

function SkeletonCard() {
  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 animate-pulse">
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-start gap-2.5 flex-1">
          <div className="mt-1.5 w-2 h-2 rounded-full bg-zinc-700 shrink-0" />
          <div className="flex-1 space-y-2">
            <div className="h-4 bg-zinc-800 rounded w-1/3" />
            <div className="h-3 bg-zinc-800 rounded w-1/5" />
          </div>
        </div>
        <div className="h-8 bg-zinc-800 rounded w-16" />
      </div>
      <div className="border-t border-zinc-800 my-3" />
      <div className="flex gap-1.5 mb-3">
        <div className="h-5 bg-zinc-800 rounded-md w-14" />
        <div className="h-5 bg-zinc-800 rounded-md w-12" />
      </div>
      <div className="h-3 bg-zinc-800 rounded w-2/3 mb-4" />
      <div className="h-1.5 bg-zinc-800 rounded-full" />
    </div>
  );
}

function SkeletonCards() {
  return (
    <div className="px-6 py-4 grid gap-3">
      <SkeletonCard />
      <SkeletonCard />
      <SkeletonCard />
    </div>
  );
}

// ─── Empty state ──────────────────────────────────────────────────────────────

function EmptyState() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center px-6">
      <Inbox className="w-10 h-10 text-zinc-700 mb-4" />
      <p className="text-zinc-400 font-medium">No offers match.</p>
      <p className="text-zinc-600 text-sm mt-1">
        Run collectors to populate, or adjust your filters.
      </p>
    </div>
  );
}

// ─── Tab definitions ──────────────────────────────────────────────────────────

const TABS: { value: FeedTab; label: string }[] = [
  { value: "all", label: "All" },
  { value: "credits", label: "Credits" },
  { value: "promos", label: "Promos" },
  { value: "models", label: "Models" },
  { value: "dead", label: "💀 Dead" },
];

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function FeedPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<FeedTab>("all");
  const [filters, setFilters] = useState<OffersFilters>(DEFAULT_FILTERS);

  // Build API params from active tab + filters
  const tabFilter = TAB_FILTERS[activeTab];
  const params: FetchOffersParams = {
    limit: 100,
    ...(tabFilter.type && { type: tabFilter.type }),
    // Tab status overrides activeOnly to avoid conflicting params
    ...(tabFilter.status
      ? { status: tabFilter.status }
      : filters.activeOnly
        ? { status: "active" }
        : {}),
    ...(filters.q && { q: filters.q }),
    ...(filters.minAmount !== "" && { min_amount: filters.minAmount }),
    ...(filters.model && { model: filters.model }),
  };

  const { data, isLoading } = useQuery({
    queryKey: apiKeys.offers(params),
    queryFn: () => fetchOffers(params),
  });

  // Client-side post-processing
  let offers = data?.items ?? [];

  if (filters.noRefOnly) {
    offers = offers.filter((o) => !o.referral_required);
  }

  if (filters.sort === "newest") {
    offers = [...offers].sort((a, b) => {
      const ta = a.first_seen_at ? new Date(a.first_seen_at).getTime() : 0;
      const tb = b.first_seen_at ? new Date(b.first_seen_at).getTime() : 0;
      return tb - ta;
    });
  } else if (filters.sort === "amount") {
    offers = [...offers].sort((a, b) => (b.amount ?? 0) - (a.amount ?? 0));
  }
  // "score" is the default API sort — no client-side sort needed

  const totalCount = data?.count ?? 0;

  function handleTabChange(value: string) {
    setActiveTab(value as FeedTab);
    // Reset activeOnly when switching to the dead tab (they conflict)
    if (value === "dead") {
      setFilters((f) => ({ ...f, activeOnly: false }));
    }
  }

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <Header
        title="Feed"
        subtitle={isLoading ? "Loading…" : `${totalCount} offers`}
      />

      <Tabs value={activeTab} onValueChange={handleTabChange}>
        <TabsList>
          {TABS.map((t) => (
            <TabsTrigger key={t.value} value={t.value}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <FeedFilters filters={filters} onChange={setFilters} />

      {/* Count indicator */}
      <div className="px-6 py-2 text-xs text-zinc-500">
        {isLoading ? (
          <span className="animate-pulse">Fetching offers…</span>
        ) : (
          `Showing ${offers.length}${offers.length !== totalCount ? ` of ${totalCount}` : ""} offers`
        )}
      </div>

      {/* Offer list */}
      {isLoading ? (
        <SkeletonCards />
      ) : offers.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="px-6 py-2 grid gap-3 pb-12">
          {offers.map((offer) => (
            <OfferCard
              key={offer.id}
              offer={offer}
              onClick={() => router.push(`/services/${offer.service_id}`)}
            />
          ))}
        </div>
      )}
    </div>
  );
}
