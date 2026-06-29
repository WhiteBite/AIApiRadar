"use client";

import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search, SlidersHorizontal, X } from "lucide-react";

import type { FeedTab, OffersFilters, Offer, SourceCategory } from "@/lib/types";
import {
  TAB_FILTERS, SOURCE_CATEGORY_MAP, SOURCE_CATEGORY_LABELS,
  OFFER_TYPE_CHIPS, AMOUNT_PRESETS, ENGINE_CHIPS,
} from "@/lib/types";
import { fetchOffers, fetchModels, apiKeys } from "@/lib/api";
import type { FetchOffersParams } from "@/lib/api";

import { Input } from "@/components/ui/input";
import { OfferList } from "@/components/feed/offer-list";
import { OfferDetail, OfferDetailEmpty } from "@/components/feed/offer-detail";
import { MODEL_COLORS } from "@/lib/colors";
import { useSaved } from "@/lib/saved";
import { cn } from "@/lib/utils";

// ── Constants ────────────────────────────────────────────────────────────────

const DEFAULT_FILTERS: OffersFilters = {
  tab: "all", q: "", minAmount: "", model: "", sort: "newest", sinceHours: 168,
  sourceCategory: "", offerType: "", noReferral: false, engine: "",
};

const TABS: { value: FeedTab; label: string; dot?: string }[] = [
  { value: "all", label: "Все" },
  { value: "easy", label: "Easy", dot: "bg-emerald-400" },
  { value: "medium", label: "Medium", dot: "bg-amber-400" },
  { value: "hard", label: "Hard", dot: "bg-red-400" },
  { value: "dead", label: "Dead" },
  { value: "saved", label: "★" },
];

const WINDOWS: { value: number | ""; label: string }[] = [
  { value: 24, label: "24ч" },
  { value: 168, label: "7д" },
  { value: 720, label: "30д" },
  { value: "", label: "Всё" },
];

const SORT_SEG: { value: OffersFilters["sort"]; label: string; title: string }[] = [
  { value: "newest", label: "Новые", title: "Сначала новые" },
  { value: "score", label: "Топ", title: "По релевантности" },
  { value: "amount", label: "$$$", title: "По сумме" },
];

// ── Chip ─────────────────────────────────────────────────────────────────────
function Chip({
  active, onClick, children, color = "default",
}: {
  active: boolean; onClick: () => void; children: React.ReactNode;
  color?: "default" | "emerald" | "blue" | "violet" | "amber";
}) {
  const base = "shrink-0 inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium transition-all cursor-pointer select-none";
  const variants: Record<string, string> = {
    default: active
      ? "bg-zinc-700 border-zinc-500 text-zinc-100 ring-1 ring-white/20"
      : "border-zinc-700 text-zinc-400 hover:text-zinc-200 hover:border-zinc-600",
    emerald: active
      ? "bg-emerald-500/15 border-emerald-500/50 text-emerald-300"
      : "border-zinc-700 text-zinc-400 hover:border-emerald-600/40 hover:text-zinc-200",
    blue: active
      ? "bg-blue-500/15 border-blue-500/50 text-blue-300"
      : "border-zinc-700 text-zinc-400 hover:border-blue-600/40 hover:text-zinc-200",
    violet: active
      ? "bg-violet-500/15 border-violet-500/50 text-violet-300"
      : "border-zinc-700 text-zinc-400 hover:border-violet-600/40 hover:text-zinc-200",
    amber: active
      ? "bg-amber-500/15 border-amber-500/50 text-amber-300"
      : "border-zinc-700 text-zinc-400 hover:border-amber-600/40 hover:text-zinc-200",
  };
  return (
    <button type="button" className={cn(base, variants[color])} onClick={onClick}>
      {children}
    </button>
  );
}

function activeFilterCount(f: OffersFilters) {
  let n = 0;
  if (f.sourceCategory) n++;
  if (f.offerType) n++;
  if (f.minAmount !== "") n++;
  if (f.engine) n++;
  if (f.noReferral) n++;
  if (f.model) n++;
  if (f.sinceHours !== 168) n++;  // non-default window
  return n;
}

// ── Page ─────────────────────────────────────────────────────────────────────
export default function FeedPage() {
  const [filters, setFilters] = useState<OffersFilters>(DEFAULT_FILTERS);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [liveOnly, setLiveOnly] = useState(false);
  const { ids: savedIds } = useSaved();

  const tabFilter = TAB_FILTERS[filters.tab];
  const params: FetchOffersParams = {
    limit: 200,
    sort: filters.sort === "newest" ? "new" : filters.sort,
    ...(tabFilter.effort && { effort: tabFilter.effort }),
    ...(tabFilter.status && { status: tabFilter.status }),
    ...(filters.q && { q: filters.q }),
    ...(filters.minAmount !== "" && { min_amount: filters.minAmount }),
    ...(filters.model && { model: filters.model }),
    ...(filters.offerType && { type: filters.offerType }),
    ...(filters.sinceHours !== "" && { since_hours: filters.sinceHours }),
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
  const topModels = (modelsData?.items ?? []).slice(0, 12);

  function update(patch: Partial<OffersFilters>) { setFilters((f) => ({ ...f, ...patch })); }
  function toggleModel(m: string) { update({ model: filters.model === m ? "" : m }); }
  function toggleSource(s: SourceCategory) { update({ sourceCategory: filters.sourceCategory === s ? "" : s }); }

  const offers = useMemo(() => {
    let list = data?.items ?? [];
    if (filters.tab === "saved") {
      const set = new Set(savedIds);
      list = list.filter((o: Offer) => set.has(o.id));
    }
    if (liveOnly) list = list.filter((o: Offer) => o.source && o.source !== "export");
    if (filters.sourceCategory) {
      const allowed = new Set(SOURCE_CATEGORY_MAP[filters.sourceCategory]);
      list = list.filter((o: Offer) => o.source && allowed.has(o.source));
    }
    if (filters.engine) list = list.filter((o: Offer) => o.engine === filters.engine);
    if (filters.noReferral) list = list.filter((o: Offer) => !o.referral_required);

    // Дедуп по домену: один лучший оффер на домен (по score). Не для вкладки dead.
    if (filters.tab !== "dead") {
      const bestByDomain = new Map<string, Offer>();
      const noDomain: Offer[] = [];
      for (const o of list) {
        if (!o.domain) { noDomain.push(o); continue; }
        const cur = bestByDomain.get(o.domain);
        if (!cur || o.score > cur.score) bestByDomain.set(o.domain, o);
      }
      list = [...bestByDomain.values(), ...noDomain];
    }

    // Сортировка
    if (filters.sort === "newest") {
      list = [...list].sort((a, b) =>
        (b.first_seen_at ? Date.parse(b.first_seen_at) : 0) -
        (a.first_seen_at ? Date.parse(a.first_seen_at) : 0));
    } else if (filters.sort === "amount") {
      list = [...list].sort((a, b) => (b.amount ?? 0) - (a.amount ?? 0));
    } else {
      list = [...list].sort((a, b) => b.score - a.score);
    }

    return list;
  }, [data, filters, savedIds, liveOnly]);

  const selectedOffer = useMemo(
    () => offers.find((o: Offer) => o.id === selectedId) ?? null,
    [offers, selectedId]
  );

  const numActive = activeFilterCount(filters);

  return (
    <div className="flex flex-col h-full overflow-hidden">

      {/* ═══ TOOLBAR ═══════════════════════════════════════════════════════ */}
      <div className="shrink-0 border-b border-zinc-800 bg-zinc-950">

        {/* Row A: tabs + search + sort + filter btn + count */}
        <div className="flex items-center gap-2 px-3 h-11">

          {/* Effort / status tabs — compact pill style */}
          <nav className="flex items-center gap-0.5 shrink-0">
            {TABS.map((t) => (
              <button
                key={t.value}
                onClick={() => update({ tab: t.value })}
                className={cn(
                  "flex items-center gap-1.5 h-7 px-3 rounded-md text-[13px] font-medium transition-colors",
                  filters.tab === t.value
                    ? "bg-zinc-700 text-zinc-100"
                    : "text-zinc-400 hover:text-zinc-300 hover:bg-zinc-800/60"
                )}
              >
                {t.dot && <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", t.dot)} />}
                {t.label}
              </button>
            ))}
          </nav>

          <div className="w-px h-5 bg-zinc-800 shrink-0" />

          {/* Search — takes remaining space */}
          <div className="relative flex-1 min-w-0 max-w-sm">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-500 pointer-events-none" />
            <Input
              placeholder="Поиск по домену, шагам…"
              value={filters.q}
              onChange={(e) => update({ q: e.target.value })}
              className="pl-8 h-8 text-[13px] bg-zinc-900 border-zinc-800 focus:border-zinc-600 w-full"
            />
            {filters.q && (
              <button onClick={() => update({ q: "" })} className="absolute right-2 top-1/2 -translate-y-1/2 text-zinc-500 hover:text-zinc-300">
                <X className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          <div className="flex-1" />

          {/* Sort — visible segment control, not dropdown */}
          <div className="flex items-center rounded-lg border border-zinc-800 overflow-hidden shrink-0">
            {SORT_SEG.map(({ value, label, title }) => (
              <button
                key={value}
                onClick={() => update({ sort: value })}
                title={title}
                className={cn(
                  "h-8 px-3 text-[13px] font-medium transition-colors border-r last:border-r-0 border-zinc-800",
                  filters.sort === value
                    ? "bg-zinc-700 text-zinc-100"
                    : "bg-transparent text-zinc-400 hover:bg-zinc-800/60 hover:text-zinc-300"
                )}
              >
                {label}
              </button>
            ))}
          </div>

          {/* Filters toggle */}
          <button
            onClick={() => setShowFilters((v) => !v)}
            title="Расширенные фильтры"
            className={cn(
              "h-8 px-2.5 rounded-lg border text-[13px] transition-colors shrink-0 flex items-center gap-1.5",
              showFilters || numActive > 0
                ? "border-blue-500/40 text-blue-300 bg-blue-500/10"
                : "border-zinc-800 text-zinc-400 hover:text-zinc-300 hover:border-zinc-700"
            )}
          >
            <SlidersHorizontal className="w-3.5 h-3.5" />
            {numActive > 0
              ? <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-blue-500 text-[10px] text-white font-bold">{numActive}</span>
              : <span className="hidden sm:inline">Фильтры</span>
            }
          </button>

          {/* Count */}
          <span className="text-[13px] text-zinc-400 tabular-nums w-8 text-right shrink-0">
            {isLoading ? "…" : offers.length}
          </span>
        </div>
      </div>

      {/* ═══ FILTER PANEL (expandable) ════════════════════════════════════ */}
      {showFilters && (
        <div className="shrink-0 border-b border-zinc-800 bg-zinc-950/90 px-4 py-3 space-y-2.5">

          {/* Window */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[12px] text-zinc-400 w-16 shrink-0">Период</span>
            {WINDOWS.map((w) => (
              <Chip key={String(w.value)} active={filters.sinceHours === w.value}
                onClick={() => update({ sinceHours: w.value })}>
                {w.label}
              </Chip>
            ))}
          </div>

          {/* Source */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[12px] text-zinc-400 w-16 shrink-0">Источник</span>
            {(Object.keys(SOURCE_CATEGORY_LABELS) as SourceCategory[]).map((cat) => (
              <Chip key={cat} active={filters.sourceCategory === cat}
                onClick={() => toggleSource(cat)} color="blue">
                {SOURCE_CATEGORY_LABELS[cat]}
              </Chip>
            ))}
          </div>

          {/* Type */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[12px] text-zinc-400 w-16 shrink-0">Тип</span>
            {OFFER_TYPE_CHIPS.map(({ value, label }) => (
              <Chip key={value} active={filters.offerType === value}
                onClick={() => update({ offerType: filters.offerType === value ? "" : value })}
                color="violet">
                {label}
              </Chip>
            ))}
          </div>

          {/* Amount */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[12px] text-zinc-400 w-16 shrink-0">Сумма</span>
            {AMOUNT_PRESETS.map(({ value, label }) => (
              <Chip key={String(value)} active={filters.minAmount === value}
                onClick={() => update({ minAmount: value })} color="emerald">
                {label}
              </Chip>
            ))}
          </div>

          {/* Engine + toggles */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-[12px] text-zinc-400 w-16 shrink-0">Движок</span>
            {ENGINE_CHIPS.map((e) => (
              <Chip key={e} active={filters.engine === e}
                onClick={() => update({ engine: filters.engine === e ? "" : e })} color="amber">
                {e}
              </Chip>
            ))}
            <span className="mx-1 text-zinc-700">·</span>
            <Chip active={filters.noReferral} onClick={() => update({ noReferral: !filters.noReferral })}>
              без реферала
            </Chip>
            <Chip active={liveOnly} onClick={() => setLiveOnly((v) => !v)}>
              только живые
            </Chip>
          </div>

          {numActive > 0 && (
            <button onClick={() => { setFilters(DEFAULT_FILTERS); setLiveOnly(false); }}
              className="flex items-center gap-1 text-[12px] text-zinc-400 hover:text-zinc-300">
              <X className="w-3 h-3" /> Сбросить фильтры
            </button>
          )}
        </div>
      )}

      {/* ═══ MODEL CHIPS ══════════════════════════════════════════════════ */}
      {topModels.length > 0 && (
        <div className="shrink-0 flex items-center gap-1.5 px-3 h-9 border-b border-zinc-800 bg-zinc-950 overflow-x-auto">
          <span className="text-[12px] text-zinc-400 shrink-0">Модель:</span>
          {topModels.map(({ model, count }) => {
            const active = filters.model === model;
            const color = MODEL_COLORS[model] ?? "bg-zinc-700/40 text-zinc-300 border-zinc-600";
            return (
              <button key={model} onClick={() => toggleModel(model)}
                className={cn(
                  "shrink-0 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[13px] font-medium transition-all",
                  active ? color + " ring-1 ring-white/30" : "border-zinc-800 text-zinc-400 hover:text-zinc-300 hover:border-zinc-700"
                )}>
                {model}
                <span className="text-[10px] opacity-60 tabular-nums">{count}</span>
              </button>
            );
          })}
          {filters.model && (
            <button onClick={() => update({ model: "" })} className="shrink-0 text-[12px] text-zinc-400 hover:text-zinc-300 ml-1">✕</button>
          )}
        </div>
      )}

      {/* ═══ BODY ══════════════════════════════════════════════════════════ */}
      <div className="flex flex-1 min-h-0 overflow-hidden">
        <div className="w-[380px] xl:w-[440px] shrink-0 border-r border-zinc-800 overflow-y-auto">
          <OfferList offers={offers} selectedId={selectedId} onSelect={setSelectedId} isLoading={isLoading} />
        </div>
        <div className="flex-1 min-w-0 overflow-hidden p-3">
          {selectedOffer
            ? <OfferDetail offer={selectedOffer} onClose={() => setSelectedId(null)} />
            : <OfferDetailEmpty />
          }
        </div>
      </div>
    </div>
  );
}
