import { cn } from "@/lib/utils";
import { TYPE_COLORS, TYPE_LABELS } from "@/lib/colors";

interface TypeBadgeProps {
  type: string;
}

export function TypeBadge({ type }: TypeBadgeProps) {
  const colorClass =
    TYPE_COLORS[type] ?? "bg-zinc-500/15 text-zinc-400 border-zinc-500/30";
  const label = TYPE_LABELS[type] ?? type;

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium",
        colorClass
      )}
    >
      {label}
    </span>
  );
}
