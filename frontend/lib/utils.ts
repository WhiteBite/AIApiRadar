import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Format relative time: "3h ago", "2d ago" */
export function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const sec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}

/** Format a lead-time delta in hours into a human string */
export function fmtLead(hours: number | null): string | null {
  if (hours === null || hours <= 0) return null;
  if (hours < 24) return `+${Math.round(hours)}h ahead`;
  return `+${Math.round(hours / 24)}d ahead`;
}

/** Clamp score 0-1 → percentage */
export function scorePct(score: number): number {
  return Math.round(Math.min(Math.max(score, 0), 1) * 100);
}

/** Format currency amount */
export function fmtAmount(amount: number | null, currency: string | null): string {
  if (!amount) return "";
  const sym = currency === "USD" || !currency ? "$" : currency + " ";
  return `${sym}${amount % 1 === 0 ? amount : amount.toFixed(0)}`;
}
