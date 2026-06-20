import { cn } from "@/lib/utils";
import { MODEL_COLORS } from "@/lib/colors";

interface ModelTagProps {
  model: string;
}

function normalizeModel(model: string): string {
  // Lowercase, then try to extract a known base name
  const lower = model.toLowerCase();
  // Known prefixes to match against
  const knownKeys = Object.keys(MODEL_COLORS);
  // Try longest-match first so "gpt-4" beats "gpt"
  const sorted = [...knownKeys].sort((a, b) => b.length - a.length);
  for (const key of sorted) {
    if (lower === key || lower.startsWith(key + "-") || lower.startsWith(key + " ")) {
      return key;
    }
  }
  // Fallback: strip version numbers and return first word
  return lower.replace(/-[\d.]+.*$/, "").split(/[\s-]/)[0];
}

function displayModel(model: string): string {
  // Capitalize first letter of the original name
  return model.charAt(0).toUpperCase() + model.slice(1);
}

export function ModelTag({ model }: ModelTagProps) {
  const key = normalizeModel(model);
  const colorClass =
    MODEL_COLORS[key] ?? "bg-zinc-700/50 text-zinc-300 border-zinc-600";

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-md border px-1.5 py-0.5 text-[11px] font-medium",
        colorClass
      )}
    >
      {displayModel(model)}
    </span>
  );
}
