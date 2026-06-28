// ─── Core types ─────────────────────────────────────────────────────────────

export type OfferType =
  | "relay" | "saas_trial" | "saas_promo" | "model_release"
  | "grant" | "abuse" | "other";

export type ServiceStatus = "new" | "active" | "dead" | "unknown";
export type EffortTier = "easy" | "medium" | "hard";
export type AmountUnit = "usd" | "credits" | "days" | "months";
export type SourceCategory = "forums" | "github" | "telegram" | "youtube" | "producthunt" | "catalogs";

export interface OfferConditions {
  requires_card?: boolean;
  requires_phone?: boolean;
  new_users_only?: boolean;
  region?: string | null;
  risk_flags?: string[];
}

export interface Offer {
  id: number;
  service_id: number;
  domain: string | null;
  name: string | null;
  type: OfferType;
  amount: number | null;
  currency: string | null;
  unit: AmountUnit | null;
  effort: EffortTier | null;
  models: string[];
  claim_steps: string | null;
  requirements: string | null;
  conditions: OfferConditions;
  description: string | null;
  referral_required: boolean;
  url: string | null;
  source: string | null;
  source_url: string | null;
  score: number;
  status: ServiceStatus;
  reliability: number | null;
  engine: string | null;
  domain_first_seen: string | null;
  first_seen_at: string | null;
  likes: number;
  dislikes: number;
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
  aliases: string[];
  domain_first_seen: string | null;
  offers: Offer[];
  signals: Signal[];
}

export interface SourceItem {
  id: number;
  name: string;
  type: string;
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
  channel: string | null;
  raw_text: string | null;
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

// ─── Filter types ────────────────────────────────────────────────────────────

export type FeedTab = "all" | "easy" | "medium" | "hard" | "dead" | "saved";

export interface OffersFilters {
  tab: FeedTab;
  q: string;
  minAmount: number | "";
  model: string;
  sort: "score" | "amount" | "newest";
  sinceHours: number | "";
  // New chip filters
  sourceCategory: SourceCategory | "";  // client-side grouping
  offerType: OfferType | "";            // passed to API
  noReferral: boolean;                  // client-side
  engine: string;                       // client-side (new-api / one-api / etc.)
}

export const TAB_FILTERS: Record<FeedTab, { effort?: string; status?: string }> = {
  all: {},
  easy: { effort: "easy" },
  medium: { effort: "medium" },
  hard: { effort: "hard" },
  dead: { status: "dead" },
  saved: {},
};

/** Sources that belong to each category — for client-side grouping */
export const SOURCE_CATEGORY_MAP: Record<SourceCategory, string[]> = {
  forums: [
    "forum_rss", "nodeseek", "linux.do", "linuxdo", "linuxdo_top", "v2ex", "hostloc",
    "reddit", "hackernews", "hackernews_ai", "hackernews_show",
    "bilibili_search_api", "bilibili_search_relay", "zhihu_topic_api",
    "csdn_search", "juejin_tag_ai", "weibo_search",
    "discord_dir",
  ],
  github: ["github", "github_lists", "github_issues", "github_code"],
  telegram: ["telegram", "telegram_ingest"],
  youtube: ["youtube"],
  producthunt: ["producthunt", "betalist", "ph_upcoming"],
  catalogs: ["directories", "coupon", "openrouter", "packages", "fofa", "leaks",
    "appsumo", "saasworthy", "futurelist", "uneed",
    "yc", "provider_lists", "changelog", "appstore", "wellfound"],
};

export const SOURCE_CATEGORY_LABELS: Record<SourceCategory, string> = {
  forums: "Форумы",
  github: "GitHub",
  telegram: "Telegram",
  youtube: "YouTube",
  producthunt: "Launches",
  catalogs: "Каталоги",
};

export const OFFER_TYPE_CHIPS: { value: OfferType; label: string }[] = [
  { value: "relay", label: "Relay" },
  { value: "saas_trial", label: "Trial" },
  { value: "saas_promo", label: "Promo" },
  { value: "grant", label: "Grant" },
  { value: "abuse", label: "Abuse" },
];

export const AMOUNT_PRESETS: { value: number | ""; label: string }[] = [
  { value: "", label: "Любая" },
  { value: 10, label: "$10+" },
  { value: 50, label: "$50+" },
  { value: 100, label: "$100+" },
  { value: 500, label: "$500+" },
];

export const ENGINE_CHIPS = ["new-api", "one-api", "sub2api"];

// ─── Display helpers ─────────────────────────────────────────────────────────

export function fmtValue(
  amount: number | null,
  unit: AmountUnit | null,
  currency: string | null,
): string {
  if (!amount) return "";
  if (unit === "credits") return `${amount.toLocaleString()}cr`;
  if (unit === "days") return `${amount}d trial`;
  if (unit === "months") return `${amount}mo`;
  const sym = currency === "USD" || !currency ? "$" : `${currency} `;
  return `${sym}${amount % 1 === 0 ? amount : amount.toFixed(0)}`;
}

export const EFFORT_LABELS: Record<EffortTier, string> = { easy: "Easy", medium: "Medium", hard: "Hard" };
export const EFFORT_EMOJI: Record<EffortTier, string> = { easy: "🟢", medium: "🟡", hard: "🔴" };
