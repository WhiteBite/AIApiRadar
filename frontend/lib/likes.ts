"use client";

import { useCallback, useEffect, useState } from "react";

const LIKES_KEY    = "airadar:likes";
const DISLIKES_KEY = "airadar:dislikes";

function readIds(key: string): Set<number> {
  if (typeof window === "undefined") return new Set();
  try {
    return new Set(JSON.parse(localStorage.getItem(key) ?? "[]") as number[]);
  } catch { return new Set(); }
}

function writeIds(key: string, ids: Set<number>) {
  try { localStorage.setItem(key, JSON.stringify([...ids])); } catch { /* quota */ }
}

export function useLikes(offerId: number) {
  const [liked,    setLiked]    = useState(false);
  const [disliked, setDisliked] = useState(false);

  // Read once from localStorage on mount (client-only)
  useEffect(() => {
    setLiked(readIds(LIKES_KEY).has(offerId));
    setDisliked(readIds(DISLIKES_KEY).has(offerId));
  }, [offerId]);

  const toggleLike = useCallback(() => {
    const likes    = readIds(LIKES_KEY);
    const dislikes = readIds(DISLIKES_KEY);
    if (likes.has(offerId)) {
      likes.delete(offerId);
      setLiked(false);
    } else {
      likes.add(offerId);
      dislikes.delete(offerId);   // like cancels dislike
      setLiked(true);
      setDisliked(false);
    }
    writeIds(LIKES_KEY, likes);
    writeIds(DISLIKES_KEY, dislikes);
  }, [offerId]);

  const toggleDislike = useCallback(() => {
    const likes    = readIds(LIKES_KEY);
    const dislikes = readIds(DISLIKES_KEY);
    if (dislikes.has(offerId)) {
      dislikes.delete(offerId);
      setDisliked(false);
    } else {
      dislikes.add(offerId);
      likes.delete(offerId);      // dislike cancels like
      setDisliked(true);
      setLiked(false);
    }
    writeIds(LIKES_KEY, likes);
    writeIds(DISLIKES_KEY, dislikes);
  }, [offerId]);

  return { liked, disliked, toggleLike, toggleDislike };
}
