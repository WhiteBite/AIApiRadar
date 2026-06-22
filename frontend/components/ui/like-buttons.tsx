"use client";

import { ThumbsUp, ThumbsDown } from "lucide-react";
import { useLikes } from "@/lib/likes";
import { cn } from "@/lib/utils";

interface LikeButtonsProps {
  offerId: number;
  initialLikes?: number;
  initialDislikes?: number;
  /** compact = small inline version for list rows */
  compact?: boolean;
}

export function LikeButtons({
  offerId, initialLikes = 0, initialDislikes = 0, compact = false,
}: LikeButtonsProps) {
  const { liked, disliked, likes, dislikes, toggleLike, toggleDislike } =
    useLikes(offerId, initialLikes, initialDislikes);

  if (compact) {
    return (
      <div className="flex items-center gap-0.5 shrink-0" onClick={(e) => e.stopPropagation()}>
        <button
          onClick={toggleLike}
          className={cn(
            "flex items-center gap-0.5 px-1 py-0.5 rounded text-[11px] transition-colors",
            liked ? "text-emerald-400" : "text-zinc-700 hover:text-zinc-400"
          )}
          title="Полезно"
        >
          <ThumbsUp className="w-3 h-3" />
          {likes > 0 && <span className="tabular-nums">{likes}</span>}
        </button>
        <button
          onClick={toggleDislike}
          className={cn(
            "flex items-center gap-0.5 px-1 py-0.5 rounded text-[11px] transition-colors",
            disliked ? "text-red-400" : "text-zinc-700 hover:text-zinc-400"
          )}
          title="Не работает"
        >
          <ThumbsDown className="w-3 h-3" />
          {dislikes > 0 && <span className="tabular-nums">{dislikes}</span>}
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
      >
        <ThumbsUp className={cn("w-4 h-4", liked && "fill-emerald-300/30")} />
        Полезно
        {likes > 0 && (
          <span className={cn(
            "ml-0.5 text-xs font-bold tabular-nums",
            liked ? "text-emerald-400" : "text-zinc-500"
          )}>
            {likes}
          </span>
        )}
      </button>
      <button
        onClick={toggleDislike}
        className={cn(
          "inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm font-medium transition-all",
          disliked
            ? "border-red-500/50 bg-red-500/10 text-red-400"
            : "border-zinc-700 text-zinc-400 hover:border-zinc-600 hover:text-zinc-200 hover:bg-zinc-800"
        )}
      >
        <ThumbsDown className={cn("w-4 h-4", disliked && "fill-red-400/30")} />
        Не работает
        {dislikes > 0 && (
          <span className={cn(
            "ml-0.5 text-xs font-bold tabular-nums",
            disliked ? "text-red-400" : "text-zinc-500"
          )}>
            {dislikes}
          </span>
        )}
      </button>
    </div>
  );
}
