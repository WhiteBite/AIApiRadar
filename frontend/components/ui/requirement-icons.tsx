import { cn } from "@/lib/utils";
import type { Offer } from "@/lib/types";

interface RequirementIconsProps {
  offer: Pick<
    Offer,
    "referral_required" | "requirements" | "claim_steps" | "effort"
  >;
  className?: string;
}

const REQ_STYLES: Record<string, string> = {
  email: "bg-zinc-500/15 text-zinc-300 border-zinc-500/30",
  referral: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  card: "bg-red-500/15 text-red-300 border-red-500/30",
  vpn: "bg-red-500/15 text-red-300 border-red-500/30",
  star: "bg-amber-500/15 text-amber-300 border-amber-500/30",
};

export function RequirementIcons({ offer, className }: RequirementIconsProps) {
  const text = (
    (offer.requirements ?? "") +
    " " +
    (offer.claim_steps ?? "")
  ).toLowerCase();

  const needs = {
    email: true,
    referral:
      offer.referral_required || /реф|referral|ref=|invite/.test(text),
    card: /карт|card|b1n|bin|namso|виртуальн/.test(text),
    vpn: /vpn|впн|vps/.test(text),
    star: /звезд|star|github star|репозитор/.test(text),
  } satisfies Record<string, boolean>;

  const items = [
    { key: "email", show: needs.email, emoji: "📧", label: "Email" },
    { key: "referral", show: needs.referral, emoji: "🔗", label: "Referral" },
    { key: "card", show: needs.card, emoji: "💳", label: "Card" },
    { key: "vpn", show: needs.vpn, emoji: "🌐", label: "VPN" },
    { key: "star", show: needs.star, emoji: "⭐", label: "Star" },
  ] as const;

  const visible = items.filter((i) => i.show);

  if (visible.length === 0) return null;

  return (
    <div className={cn("flex flex-wrap gap-1.5", className)}>
      {visible.map(({ key, emoji, label }) => (
        <span
          key={key}
          className={cn(
            "inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-xs font-medium",
            REQ_STYLES[key]
          )}
        >
          <span aria-hidden="true">{emoji}</span>
          {label}
        </span>
      ))}
    </div>
  );
}
