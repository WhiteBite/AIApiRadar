"use client";

import { useCallback, useEffect, useState } from "react";

const KEY = "aiapiradar:saved";

/** Local-first saved/bookmarked offers (persisted in localStorage). */
export function useSaved() {
  const [ids, setIds] = useState<number[]>([]);

  useEffect(() => {
    try {
      setIds(JSON.parse(localStorage.getItem(KEY) || "[]"));
    } catch {
      setIds([]);
    }
  }, []);

  const persist = (next: number[]) => {
    setIds(next);
    try {
      localStorage.setItem(KEY, JSON.stringify(next));
    } catch {
      /* ignore quota errors */
    }
  };

  const toggle = useCallback((id: number) => {
    setIds((prev) => {
      const next = prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id];
      try {
        localStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        /* ignore */
      }
      return next;
    });
  }, []);

  const isSaved = useCallback((id: number) => ids.includes(id), [ids]);

  return { ids, toggle, isSaved, persist };
}
