"""Canonical collector metadata — single source of truth.

`COLLECTOR_META` maps each collector name to its human-readable label, a color
dot for the settings UI, and the env var it requires (if any). `web.py` imports
this (as `_COLLECTOR_META`) and `scripts/gen_worker_constants.py` renders it into
`worker/src/_generated.ts`, so the Python copy is authoritative and the worker
copy is generated — no more hand-maintained drift between the two.

`STREAM_COLLECTORS` lists collectors that run in streaming (push) mode rather
than polling.
"""
from __future__ import annotations

# key = collector name, maps to label + color dot + required env var (if any).
COLLECTOR_META: dict[str, dict] = {
    "certstream":   {"label": "CertStream (CT-логи)",          "dot": "cyan",   "requires": None},
    "crtsh":        {"label": "crt.sh (новые домены)",          "dot": "cyan",   "requires": None},
    "forum_rss":    {"label": "Форумы (nodeseek / linux.do / v2ex / RSSHub)", "dot": "orange", "requires": None},
    "hackernews":   {"label": "Hacker News",                    "dot": "orange", "requires": None},
    "reddit":       {"label": "Reddit",                         "dot": "orange", "requires": None},
    "github":       {"label": "GitHub",                         "dot": "zinc",   "requires": "AIRADAR_GITHUB_TOKEN"},
    "github_lists": {"label": "GitHub awesome-lists",           "dot": "zinc",   "requires": "AIRADAR_GITHUB_TOKEN"},
    "huggingface":  {"label": "HuggingFace (релизы моделей)",   "dot": "yellow", "requires": None},
    "producthunt":  {"label": "Product Hunt",                   "dot": "red",    "requires": None},
    "directories":  {"label": "AI-каталоги (BetaList/Uneed…)",  "dot": "lime",   "requires": None},
    "coupon":       {"label": "Агрегаторы сделок (AppSumo…)",   "dot": "purple", "requires": None},
    "youtube":      {"label": "YouTube",                        "dot": "red",    "requires": "AIRADAR_YOUTUBE_API_KEY"},
    "searchdorks":  {"label": "Search dorks (Google CSE)",      "dot": "blue",   "requires": "AIRADAR_SEARCH_API_KEY"},
    "twitter":      {"label": "Twitter / X",                    "dot": "sky",    "requires": "AIRADAR_TW_BEARER_TOKEN"},
    "telegram":     {"label": "Telegram ingest",                "dot": "sky",    "requires": "AIRADAR_TG_API_ID"},
    "openrouter":   {"label": "OpenRouter (каталог моделей)",   "dot": "violet", "requires": None},
    "packages":     {"label": "npm / PyPI (AI SDK пакеты)",     "dot": "zinc",   "requires": None},
    "fofa":         {"label": "FOFA (favicon-hash сканер)",     "dot": "red",    "requires": "AIRADAR_FOFA_KEY"},
    "leaks":        {"label": "Gists / Pastebin (утечки)",      "dot": "zinc",   "requires": "AIRADAR_GITHUB_TOKEN"},
    "yc":           {"label": "Y Combinator (AI-стартапы)",     "dot": "orange", "requires": None},
    "provider_lists": {"label": "Provider-листы (litellm)",     "dot": "violet", "requires": None},
    "changelog_rss": {"label": "Changelog/blog RSS (платформы)", "dot": "lime",  "requires": None},
    "appstore":     {"label": "App Store (новые AI-приложения)", "dot": "blue",  "requires": None},
    "ph_upcoming":  {"label": "Product Hunt (newest/upcoming)",  "dot": "red",   "requires": "AIRADAR_PH_TOKEN"},
    "wellfound":    {"label": "Wellfound (AI-стартапы, ML-вакансии)", "dot": "lime", "requires": None},
    "discord_dir":  {"label": "Discord-каталоги (disboard)",     "dot": "indigo", "requires": None},
}

# Collectors that run in streaming (push) mode rather than polling.
STREAM_COLLECTORS: set[str] = {"certstream", "telegram"}
