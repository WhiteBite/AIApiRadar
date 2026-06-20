import { Trophy } from "lucide-react";
import { fmtLead } from "@/lib/utils";

interface LeadBadgeProps {
  leadHours: number | null;
}

export function LeadBadge({ leadHours }: LeadBadgeProps) {
  const label = fmtLead(leadHours);
  if (!label) return null;

  return (
    <span className="inline-flex items-center gap-1 rounded-full border bg-amber-500/15 text-amber-300 border-amber-500/30 px-2 py-0.5 text-xs font-medium">
      <Trophy className="w-3 h-3 shrink-0" />
      {label}
    </span>
  );
}
