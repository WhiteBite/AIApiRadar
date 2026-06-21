// ─── Core types — shared contract for all agents ───────────────────────────
// These mirror the FastAPI /api/* response shapes.

export type OfferType =
  | "relay"
  | "saas_trial"
  | "saas_promo"
  | "model_release"
  | "grant"
  | "abuse"
  | "other";

export type ServiceStatus = "new" | "active" | "dead" | "unknown";

/** How much effort is required to claim the offer. */
export type EffortTier = "easy" | "medium" | "hard";

/**
 * Unit of the amount field.
 * usd     → "$200"
 * credits → "5 000cr"
 * days    → "7d trial"
 * months  → "3 months"
 */
export type AmountUnit = "usd" | "credits" | "days" | "months";

export interface Offer {
  id: number;
  service_id: number;
  domain: string | null;
  name: string | null;
  type: OfferType;
  amount: number | null;
  currency: string | null;
  unit: AmountUnit | null;      // NEW — how to interpret amount
  effort: EffortTier | null;    // NEW — easy / medium / hard to claim
  models: string[];
  claim_steps: string | null;
  requirements: string | null;
  referral_required: boolean;
  url: string | null;
  source: string | null;        // NEW — collector that found it (certstream, telegram…)
  source_url: string | null;    // NEW — link to the original post/page
  score: number;
  status: ServiceStatus;
  reliability: number | null;
  engine: string | null;
  domain_first_seen: string | null;
  first_seen_at: string | null;
}

export interface OffersResponse {
  count: number;
  items: Offer[];
}

export interface Service {
  id: number;
  domain: string;
  name: string | null;
  type: OfferType;
  engine: string | null;
  status: ServiceStatus;
  reliability: number;
  aliases: string[];            // NEW — other hosts merged into this entity
  domain_first_seen: string | null;
  offers: Offer[];
  signals: Signal[];
}

export interface SourceItem {
  id: number;
  name: string;
  type: string;                 // "telegram" | "rss" | "collector"
  enabled: boolean;
  last_run: string | null;
  config: { channel?: string; topic_id?: number } & Record<string, unknown>;
}

export interface ModelCount {
  model: string;
  count: number;
}

export interface Signal {
  source: string;
  source_url: string | null;
  channel: string | null;       // NEW — @channel parsed from t.me url
  raw_text: string | null;      // NEW — original post text
  observed_at: string | null;
}

export interface Stats {
  services: number;
  offers: number;
  active: number;
  dead: number;
  by_type: Partial<Record<OfferType, number>>;
  by_effort?: Partial<Record<EffortTier, number>>;
}

// ─── UI helpers ─────────────────────────────────────────────────────────────

export type FeedTab = "all" | "easy" | "medium" | "hard" | "dead" | "saved";

export interface OffersFilters {
  tab: FeedTab;
  q: string;
  minAmount: number | "";
  model: string;
  sort: "score" | "amount" | "newest";
}

// Map tab → API params
export const TAB_FILTERS: Record<FeedTab, { effort?: string; status?: string }> = {
  all: {},
  easy: { effort: "easy" },
  medium: { effort: "medium" },
  hard: { effort: "hard" },
  dead: { status: "dead" },
  saved: {},
};

// ─── Display helpers ─────────────────────────────────────────────────────────

/** Format amount+unit into a human-readable string. */
export function fmtValue(
  amount: number | null,
  unit: AmountUnit | null,
  currency: string | null
): string {
  if (!amount) return "";
  if (unit === "credits") return `${amount.toLocaleString()}cr`;
  if (unit === "days") return `${amount}d trial`;
  if (unit === "months") return `${amount}mo`;
  // usd or fallback
  const sym = currency === "USD" || !currency ? "$" : `${currency} `;
  return `${sym}${amount % 1 === 0 ? amount : amount.toFixed(0)}`;
}

/** Effort tier → human label */
export const EFFORT_LABELS: Record<EffortTier, string> = {
  easy: "Easy",
  medium: "Medium",
  hard: "Hard",
};

/** Effort tier → emoji indicator */
export const EFFORT_EMOJI: Record<EffortTier, string> = {
  easy: "🟢",
  medium: "🟡",
  hard: "🔴",
};
