// ─── Design-system color tokens ────────────────────────────────────────────
// Use these constants everywhere — no raw hex strings in components.

export const MODEL_COLORS: Record<string, string> = {
  claude:   "bg-violet-500/15 text-violet-300 border-violet-500/30",
  opus:     "bg-violet-500/15 text-violet-300 border-violet-500/30",
  sonnet:   "bg-violet-400/15 text-violet-300 border-violet-400/30",
  haiku:    "bg-violet-300/15 text-violet-300 border-violet-300/30",
  gpt:      "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  "gpt-4":  "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  o1:       "bg-emerald-400/15 text-emerald-300 border-emerald-400/30",
  o3:       "bg-emerald-400/15 text-emerald-300 border-emerald-400/30",
  gemini:   "bg-blue-500/15 text-blue-300 border-blue-500/30",
  glm:      "bg-amber-500/15 text-amber-300 border-amber-500/30",
  deepseek: "bg-red-500/15 text-red-300 border-red-500/30",
  qwen:     "bg-orange-500/15 text-orange-300 border-orange-500/30",
  mistral:  "bg-pink-500/15 text-pink-300 border-pink-500/30",
  llama:    "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
  grok:     "bg-teal-500/15 text-teal-300 border-teal-500/30",
};

export const SOURCE_COLORS: Record<string, string> = {
  certstream:   "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
  forum_rss:    "bg-orange-500/15 text-orange-300 border-orange-500/30",
  nodeseek:     "bg-orange-500/15 text-orange-300 border-orange-500/30",
  linuxdo:      "bg-orange-400/15 text-orange-300 border-orange-400/30",
  v2ex:         "bg-orange-400/15 text-orange-300 border-orange-400/30",
  github:       "bg-zinc-500/15 text-zinc-300 border-zinc-500/30",
  huggingface:  "bg-yellow-500/15 text-yellow-300 border-yellow-500/30",
  producthunt:  "bg-red-400/15 text-red-300 border-red-400/30",
  directories:  "bg-lime-500/15 text-lime-300 border-lime-500/30",
  coupon:       "bg-purple-500/15 text-purple-300 border-purple-500/30",
  telegram:     "bg-sky-500/15 text-sky-300 border-sky-500/30",
  youtube:      "bg-red-500/15 text-red-300 border-red-500/30",
  export:       "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
};

export const TYPE_COLORS: Record<string, string> = {
  relay:         "bg-red-500/15 text-red-300 border-red-500/30",
  saas_trial:    "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  saas_promo:    "bg-violet-500/15 text-violet-300 border-violet-500/30",
  model_release: "bg-blue-500/15 text-blue-300 border-blue-500/30",
  grant:         "bg-amber-500/15 text-amber-300 border-amber-500/30",
  abuse:         "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
  other:         "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
};

export const STATUS_COLORS: Record<string, string> = {
  active:  "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
  dead:    "bg-red-500/15 text-red-300 border-red-500/30",
  new:     "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
  unknown: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
};

export const STATUS_DOT: Record<string, string> = {
  active:  "bg-emerald-400",
  dead:    "bg-red-400",
  new:     "bg-zinc-500",
  unknown: "bg-zinc-500",
};

/** Human-readable offer type labels */
export const TYPE_LABELS: Record<string, string> = {
  relay:         "Relay (中转站)",
  saas_trial:    "SaaS Trial",
  saas_promo:    "Promo",
  model_release: "Model Release",
  grant:         "Grant",
  abuse:         "Method",
  other:         "Other",
};
