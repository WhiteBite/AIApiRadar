import { cn } from "@/lib/utils";
import { scorePct } from "@/lib/utils";

interface ScoreBarProps {
  score: number;
  showLabel?: boolean;
  className?: string;
}

function getFillClass(score: number): string {
  if (score < 0.4) return "bg-red-500";
  if (score < 0.6) return "bg-amber-500";
  if (score < 0.8) return "bg-blue-500";
  return "bg-emerald-500";
}

export function ScoreBar({ score, showLabel = true, className }: ScoreBarProps) {
  const pct = scorePct(score);
  const fillClass = getFillClass(score);

  return (
    <div className={cn("flex items-center gap-2", className)}>
      <div className="flex-1 bg-zinc-800 rounded-full h-1.5 overflow-hidden">
        <div
          className={cn("h-full rounded-full transition-all duration-300", fillClass)}
          style={{ width: `${pct}%` }}
        />
      </div>
      {showLabel && (
        <span className="text-xs text-zinc-400 tabular-nums w-8 text-right shrink-0">
          {score.toFixed(2)}
        </span>
      )}
    </div>
  );
}
