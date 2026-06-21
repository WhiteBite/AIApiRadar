"use client";

import { useState } from "react";

interface FaviconProps {
  domain: string | null;
  size?: number;
  className?: string;
}

/** Service favicon via DuckDuckGo icon API with letter-avatar fallback. */
export function Favicon({ domain, size = 16, className = "" }: FaviconProps) {
  const [broken, setBroken] = useState(false);

  if (!domain || broken) {
    const letter = (domain ?? "?")[0].toUpperCase();
    return (
      <span
        className={`inline-flex items-center justify-center rounded-sm bg-zinc-700 text-zinc-300 font-medium select-none ${className}`}
        style={{ width: size, height: size, fontSize: size * 0.6 }}
      >
        {letter}
      </span>
    );
  }

  return (
    <img
      src={`https://icons.duckduckgo.com/ip3/${domain}.ico`}
      alt=""
      width={size}
      height={size}
      onError={() => setBroken(true)}
      className={`rounded-sm object-contain ${className}`}
      style={{ width: size, height: size }}
    />
  );
}
