import { cn } from "@/lib/utils";
import { SOURCE_COLORS } from "@/lib/colors";

interface SourceBadgeProps {
  source: string;
}

const SOURCE_LABELS: Record<string, string> = {
  certstream: "CT Logs",
  forum_rss: "Forum RSS",
  nodeseek: "NodeSeek",
  linuxdo: "linux.do",
  github: "GitHub",
  huggingface: "HuggingFace",
  producthunt: "Product Hunt",
  directories: "Directories",
  coupon: "Coupon",
  telegram: "Telegram",
  export: "Архив (чат)",
  youtube: "YouTube",
  v2ex: "v2ex",
  crtsh: "CT Logs",
};

function getDisplayName(source: string): string {
  if (SOURCE_LABELS[source]) return SOURCE_LABELS[source];
  // Capitalize first letter as fallback
  return source.charAt(0).toUpperCase() + source.slice(1);
}

export function SourceBadge({ source }: SourceBadgeProps) {
  const colorClass =
    SOURCE_COLORS[source] ?? "bg-zinc-500/15 text-zinc-400 border-zinc-500/30";

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium",
        colorClass
      )}
    >
      {getDisplayName(source)}
    </span>
  );
}
