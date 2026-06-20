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

export interface Offer {
  id: number;
  service_id: number;
  domain: string | null;
  name: string | null;
  type: OfferType;
  amount: number | null;
  currency: string | null;
  models: string[];
  claim_steps: string | null;
  requirements: string | null;
  referral_required: boolean;
  url: string | null;
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
  domain_first_seen: string | null;
  offers: Offer[];
  signals: Signal[];
}

export interface Signal {
  source: string;
  source_url: string | null;
  observed_at: string | null;
}

export interface Stats {
  services: number;
  offers: number;
  active: number;
  dead: number;
  by_type: Partial<Record<OfferType, number>>;
}

// ─── UI helpers ─────────────────────────────────────────────────────────────

export type FeedTab = "all" | "credits" | "promos" | "models" | "dead";

export interface OffersFilters {
  tab: FeedTab;
  q: string;
  minAmount: number | "";
  model: string;
  activeOnly: boolean;
  noRefOnly: boolean;
  sort: "score" | "amount" | "newest";
}

// Map tab → API params
export const TAB_FILTERS: Record<
  FeedTab,
  { type?: string; status?: string }
> = {
  all: {},
  credits: { type: "relay" },      // combined in page component
  promos: { type: "saas_promo" },
  models: { type: "model_release" },
  dead: { status: "dead" },
};
