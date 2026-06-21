import { cn } from "@/lib/utils";
import { EFFORT_COLORS, EFFORT_DOT, EFFORT_BG } from "@/lib/colors";
import { EFFORT_LABELS, EFFORT_EMOJI } from "@/lib/types";
import type { EffortTier } from "@/lib/types";

interface EffortBadgeProps {
  effort: EffortTier | null;
  variant?: "dot" | "pill" | "full";
  className?: string;
}

export function EffortBadge({
  effort,
  variant = "full",
  className,
}: EffortBadgeProps) {
  const dotClass = effort ? EFFORT_DOT[effort] : "bg-zinc-500";
  const bgClass = effort
    ? EFFORT_BG[effort]
    : "bg-zinc-500/10 text-zinc-400 border-zinc-500/25";
  const textClass = effort ? EFFORT_COLORS[effort] : "text-zinc-400";
  const label = effort ? EFFORT_LABELS[effort] : "Unknown";
  const emoji = effort ? EFFORT_EMOJI[effort] : "⚪";

  if (variant === "dot") {
    return (
      <span
        className={cn("w-2 h-2 rounded-full shrink-0", dotClass, className)}
      />
    );
  }

  if (variant === "pill") {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium",
          bgClass,
          className
        )}
      >
        <span aria-hidden="true">{emoji}</span>
        {label}
      </span>
    );
  }

  // "full" variant: dot + label text
  return (
    <span className={cn("inline-flex items-center gap-1.5", className)}>
      <span className={cn("w-2 h-2 rounded-full shrink-0", dotClass)} />
      <span className={cn("text-xs font-medium", textClass)}>{label}</span>
    </span>
  );
}
