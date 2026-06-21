import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** Relative time in Russian: "только что", "5 мин назад", "3 ч назад", "2 дн назад" */
export function timeAgo(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const sec = Math.floor((Date.now() - d.getTime()) / 1000);
  if (!Number.isFinite(sec) || sec < 0) return "только что";
  if (sec < 60) return "только что";
  if (sec < 3600) return `${Math.floor(sec / 60)} мин назад`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} ч назад`;
  return `${Math.floor(sec / 86400)} дн назад`;
}

/** True if the ISO timestamp is within the last `hours` hours. */
export function isWithinHours(iso: string | null, hours: number): boolean {
  if (!iso) return false;
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return false;
  return Date.now() - t < hours * 3.6e6;
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
