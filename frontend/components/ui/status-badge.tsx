import { cn } from "@/lib/utils";
import { STATUS_COLORS, STATUS_DOT } from "@/lib/colors";
import type { ServiceStatus } from "@/lib/types";

interface StatusBadgeProps {
  status: ServiceStatus;
  showDot?: boolean;
}

const STATUS_LABELS: Record<ServiceStatus, string> = {
  active: "Active",
  dead: "Dead",
  new: "New",
  unknown: "Unknown",
};

export function StatusBadge({ status, showDot = true }: StatusBadgeProps) {
  const colorClass =
    STATUS_COLORS[status] ?? "bg-zinc-500/15 text-zinc-400 border-zinc-500/30";
  const dotClass = STATUS_DOT[status] ?? "bg-zinc-500";

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs",
        colorClass
      )}
    >
      {showDot && (
        <span className={cn("w-1.5 h-1.5 rounded-full shrink-0", dotClass)} />
      )}
      {STATUS_LABELS[status]}
    </span>
  );
}
