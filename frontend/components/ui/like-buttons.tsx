"use client";

import { ThumbsUp, ThumbsDown } from "lucide-react";
import { useLikes } from "@/lib/likes";
import { cn } from "@/lib/utils";

interface LikeButtonsProps {
  offerId: number;
  /** compact = small inline version for list rows */
  compact?: boolean;
}

export function LikeButtons({ offerId, compact = false }: LikeButtonsProps) {
  const { liked, disliked, toggleLike, toggleDislike } = useLikes(offerId);

  if (compact) {
    return (
      <div className="flex items-center gap-1 shrink-0" onClick={(e) => e.stopPropagation()}>
        <button
          onClick={toggleLike}
          className={cn(
            "p-1 rounded transition-colors",
            liked
              ? "text-emerald-400"
              : "text-zinc-700 hover:text-zinc-400"
          )}
          title="Полезно"
        >
          <ThumbsUp className="w-3 h-3" />
        </button>
        <button
          onClick={toggleDislike}
          className={cn(
            "p-1 rounded transition-colors",
            disliked
              ? "text-red-400"
              : "text-zinc-700 hover:text-zinc-400"
          )}
          title="Не полезно"
        >
          <ThumbsDown className="w-3 h-3" />
        </button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={toggleLike}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition-all",
          liked
            ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-300"
            : "border-zinc-700 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200 hover:bg-zinc-800"
        )}
        title="Полезный оффер"
      >
        <ThumbsUp className={cn("w-4 h-4", liked && "fill-emerald-300/30")} />
        Полезно
      </button>
      <button
        onClick={toggleDislike}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition-all",
          disliked
            ? "border-red-500/50 bg-red-500/10 text-red-400"
            : "border-zinc-700 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200 hover:bg-zinc-800"
        )}
        title="Не работает / мусор"
      >
        <ThumbsDown className={cn("w-4 h-4", disliked && "fill-red-400/30")} />
        Не работает
      </button>
    </div>
  );
}
