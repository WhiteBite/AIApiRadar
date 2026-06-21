import type { Offer, OffersResponse, Service, Stats } from "./types";

// Server components (RSC/SSR) need an absolute URL.
// Client components use relative paths → Next.js rewrites proxy them to FastAPI
// without any CORS issues.
function resolveUrl(path: string, params?: Record<string, string | number | boolean | undefined>): string {
  const isServer = typeof window === "undefined";
  const base = isServer
    ? (process.env.API_URL ?? "http://127.0.0.1:8000")
    : "";

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

// TanStack Query cache keys
export const apiKeys = {
  offers: (p: FetchOffersParams) => ["offers", p] as const,
  service: (id: number) => ["service", id] as const,
  stats: () => ["stats"] as const,
};
