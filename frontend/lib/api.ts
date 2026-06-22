import type { Offer, OffersResponse, Service, Stats, SourceItem, ModelCount } from "./types";

// Server components (RSC/SSR) need an absolute URL.
// Client components use relative paths → Next.js rewrites proxy them to FastAPI
// without any CORS issues.
function resolveUrl(path: string, params?: Record<string, string | number | boolean | undefined>): string {
  const isServer = typeof window === "undefined";
  // Client: use absolute API URL in production (static export, no rewrite proxy);
  // empty in dev so relative paths hit the Next.js rewrite proxy (no CORS).
  // Server (dev SSR): absolute backend URL.
  const base = isServer
    ? (process.env.API_URL ?? "http://127.0.0.1:8000")
    : (process.env.NEXT_PUBLIC_API_URL ?? "");

  // Build query string
  const qs = params
    ? Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== "" && v !== null)
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
      .join("&")
    : "";

  const full = `${base}${path}${qs ? "?" + qs : ""}`;
  return full;
}

async function get<T>(path: string, params?: Record<string, string | number | boolean | undefined>): Promise<T> {
  const url = resolveUrl(path, params);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export interface FetchOffersParams {
  type?: string;
  effort?: string;
  min_amount?: number | "";
  model?: string;
  status?: string;
  q?: string;
  sort?: string;
  since_hours?: number;
  limit?: number;
  offset?: number;
}

export async function fetchOffers(params: FetchOffersParams = {}): Promise<OffersResponse> {
  return get<OffersResponse>("/api/offers", {
    ...params,
    min_amount: params.min_amount || undefined,
  });
}

export async function fetchService(id: number): Promise<Service> {
  return get<Service>(`/api/services/${id}`);
}

export async function fetchStats(): Promise<Stats> {
  return get<Stats>("/api/stats");
}

export async function fetchModels(): Promise<{ items: ModelCount[] }> {
  return get<{ items: ModelCount[] }>("/api/models");
}

export async function fetchSources(type?: string): Promise<{ items: SourceItem[] }> {
  return get<{ items: SourceItem[] }>("/api/sources", type ? { type } : undefined);
}

async function mutate<T>(path: string, method: string, body?: unknown): Promise<T> {
  const base = typeof window === "undefined"
    ? (process.env.API_URL ?? "http://127.0.0.1:8000")
    : (process.env.NEXT_PUBLIC_API_URL ?? "");
  const res = await fetch(`${base}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`API ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export async function createSource(body: {
  type: string; channel?: string; topic_id?: number; enabled?: boolean;
}): Promise<SourceItem> {
  return mutate<SourceItem>("/api/sources", "POST", body);
}

export async function updateSource(
  id: number, body: { enabled?: boolean; config?: object; name?: string }
): Promise<SourceItem> {
  return mutate<SourceItem>(`/api/sources/${id}`, "PATCH", body);
}

export async function deleteSource(id: number): Promise<void> {
  await mutate(`/api/sources/${id}`, "DELETE");
}

export interface Analytics {
  lead_time: {
    avg_hours: number | null;
    median_hours: number | null;
    count_ahead: number;
    count_total: number;
  };
  by_source: Array<{ source: string; count: number }>;
  with_description: number;
  offers_total: number;
}

export async function fetchAnalytics(): Promise<Analytics> {
  return get<Analytics>('/api/analytics');
}

export interface VoteResult { likes: number; dislikes: number; my_vote: number }

export async function castVote(offerId: number, vote: 1 | -1 | 0): Promise<VoteResult> {
  return mutate<VoteResult>(`/api/offers/${offerId}/vote`, 'POST', { vote });
}

export async function fetchMyVote(offerId: number): Promise<{ my_vote: number }> {
  return get<{ my_vote: number }>(`/api/offers/${offerId}/my-vote`);
}

// TanStack Query cache keys
export const apiKeys = {
  offers: (p: FetchOffersParams) => ["offers", p] as const,
  service: (id: number) => ["service", id] as const,
  stats: () => ["stats"] as const,
  models: () => ["models"] as const,
  sources: () => ["sources"] as const,
  analytics: () => ["analytics"] as const,
  collectors: () => ["collectors"] as const,
  keyStatus: () => ["key-status"] as const,
  settings: () => ["settings"] as const,
};

export interface CollectorItem {
  name: string;
  label: string;
  dot: string;
  kind: string;
  mode: "poll" | "stream";
  interval: number;
  enabled: boolean;
  requires: string | null;
  key_present: boolean | null;
}

export interface KeyStatus {
  key: string;
  present: boolean;
  unlocks: string[];
}

export async function fetchCollectors(): Promise<CollectorItem[]> {
  return get<CollectorItem[]>('/api/collectors');
}

export async function patchCollector(
  name: string, body: { enabled?: boolean; interval?: number }
): Promise<{ ok: boolean }> {
  return mutate<{ ok: boolean }>(`/api/collectors/${name}`, 'PATCH', body);
}

export async function fetchKeyStatus(): Promise<KeyStatus[]> {
  return get<KeyStatus[]>('/api/keys');
}

// ── App settings ──────────────────────────────────────────────────────────────

export interface AppSettings {
  prefilter_en_strong: string[];
  prefilter_en_weak: string[];
  prefilter_ru: string[];
  prefilter_zh_strong: string[];
  prefilter_zh_weak: string[];
  score_w_freshness: number;
  score_w_amount: number;
  score_w_ease: number;
  score_w_reliability: number;
  early_signal_boost: number;
  discovery_limit: number;
  notify_min_score: number;
}

export async function fetchSettings(): Promise<AppSettings> {
  return get<AppSettings>('/api/settings');
}

export async function patchSettings(patch: Partial<AppSettings>): Promise<{ ok: boolean }> {
  return mutate<{ ok: boolean }>('/api/settings', 'PATCH', patch);
}
