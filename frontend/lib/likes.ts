"use client";

import { useCallback, useEffect, useState } from "react";
import { castVote, fetchMyVote } from "@/lib/api";

// localStorage keys — used only for optimistic UI while the server responds.
const LS_LIKES = "airadar:likes";
const LS_DISLIKES = "airadar:dislikes";

function readIds(key: string): Set<number> {
  if (typeof window === "undefined") return new Set();
  try { return new Set(JSON.parse(localStorage.getItem(key) ?? "[]") as number[]); }
  catch { return new Set(); }
}
function writeIds(key: string, ids: Set<number>) {
  try { localStorage.setItem(key, JSON.stringify([...ids])); } catch { /* quota */ }
}

export function useLikes(offerId: number, initialLikes = 0, initialDislikes = 0) {
  // Optimistic local state — updated immediately on click
  const [liked, setLiked] = useState(() => readIds(LS_LIKES).has(offerId));
  const [disliked, setDisliked] = useState(() => readIds(LS_DISLIKES).has(offerId));
  // Server-authoritative counts shown to all visitors
  const [likes, setLikes] = useState(initialLikes);
  const [dislikes, setDislikes] = useState(initialDislikes);

  // On mount: sync my vote from the server (overrides stale localStorage)
  useEffect(() => {
    fetchMyVote(offerId)
      .then(({ my_vote }) => {
        const l = my_vote === 1;
        const d = my_vote === -1;
        setLiked(l);
        setDisliked(d);
        // Keep localStorage in sync
        const likes = readIds(LS_LIKES);
        const dislikes = readIds(LS_DISLIKES);
        if (l) { likes.add(offerId); dislikes.delete(offerId); }
        else { likes.delete(offerId); }
        if (d) { dislikes.add(offerId); likes.delete(offerId); }
        else { dislikes.delete(offerId); }
        writeIds(LS_LIKES, likes);
        writeIds(LS_DISLIKES, dislikes);
      })
      .catch(() => { /* server unavailable — keep localStorage state */ });
  }, [offerId]);

  // Keep server counts in sync when initialLikes/Dislikes change (offer re-fetched)
  useEffect(() => { setLikes(initialLikes); }, [initialLikes]);
  useEffect(() => { setDislikes(initialDislikes); }, [initialDislikes]);

  const vote = useCallback(async (v: 1 | -1 | 0) => {
    // Optimistic UI
    const isLike = v === 1;
    const isDislike = v === -1;
    setLiked(isLike);
    setDisliked(isDislike);

    const ls = readIds(LS_LIKES);
    const ld = readIds(LS_DISLIKES);
    if (isLike) { ls.add(offerId); ld.delete(offerId); }
    else { ls.delete(offerId); }
    if (isDislike) { ld.add(offerId); ls.delete(offerId); }
    else { ld.delete(offerId); }
    writeIds(LS_LIKES, ls);
    writeIds(LS_DISLIKES, ld);

    // Server write — update counts on success
    try {
      const res = await castVote(offerId, v);
      setLikes(res.likes);
      setDislikes(res.dislikes);
    } catch { /* keep optimistic state */ }
  }, [offerId]);

  const toggleLike = useCallback(() => vote(liked ? 0 : 1), [liked, vote]);
  const toggleDislike = useCallback(() => vote(disliked ? 0 : -1), [disliked, vote]);

  return { liked, disliked, likes, dislikes, toggleLike, toggleDislike };
}
