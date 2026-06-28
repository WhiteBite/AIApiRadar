// AUTO-GENERATED from aiapiradar/collector_meta.py + app_defaults.py.
// Do not edit by hand — regenerate with:  python -m scripts.gen_worker_constants

export const COLLECTOR_META: Record<string, { label: string; dot: string; requires: string | null }> = {
  "certstream": { label: "CertStream (CT-логи)", dot: "cyan", requires: null },
  "crtsh": { label: "crt.sh (новые домены)", dot: "cyan", requires: null },
  "forum_rss": { label: "Форумы (nodeseek / linux.do / v2ex / RSSHub)", dot: "orange", requires: null },
  "hackernews": { label: "Hacker News", dot: "orange", requires: null },
  "reddit": { label: "Reddit", dot: "orange", requires: null },
  "github": { label: "GitHub", dot: "zinc", requires: "AIRADAR_GITHUB_TOKEN" },
  "github_lists": { label: "GitHub awesome-lists", dot: "zinc", requires: "AIRADAR_GITHUB_TOKEN" },
  "huggingface": { label: "HuggingFace (релизы моделей)", dot: "yellow", requires: null },
  "producthunt": { label: "Product Hunt", dot: "red", requires: null },
  "directories": { label: "AI-каталоги (BetaList/Uneed…)", dot: "lime", requires: null },
  "coupon": { label: "Агрегаторы сделок (AppSumo…)", dot: "purple", requires: null },
  "youtube": { label: "YouTube", dot: "red", requires: "AIRADAR_YOUTUBE_API_KEY" },
  "searchdorks": { label: "Search dorks (Google CSE)", dot: "blue", requires: "AIRADAR_SEARCH_API_KEY" },
  "twitter": { label: "Twitter / X", dot: "sky", requires: "AIRADAR_TW_BEARER_TOKEN" },
  "telegram": { label: "Telegram ingest", dot: "sky", requires: "AIRADAR_TG_API_ID" },
  "openrouter": { label: "OpenRouter (каталог моделей)", dot: "violet", requires: null },
  "packages": { label: "npm / PyPI (AI SDK пакеты)", dot: "zinc", requires: null },
  "fofa": { label: "FOFA (favicon-hash сканер)", dot: "red", requires: "AIRADAR_FOFA_KEY" },
  "leaks": { label: "Gists / Pastebin (утечки)", dot: "zinc", requires: "AIRADAR_GITHUB_TOKEN" },
  "yc": { label: "Y Combinator (AI-стартапы)", dot: "orange", requires: null },
  "provider_lists": { label: "Provider-листы (litellm)", dot: "violet", requires: null },
  "changelog_rss": { label: "Changelog/blog RSS (платформы)", dot: "lime", requires: null },
  "appstore": { label: "App Store (новые AI-приложения)", dot: "blue", requires: null },
  "ph_upcoming": { label: "Product Hunt (newest/upcoming)", dot: "red", requires: "AIRADAR_PH_TOKEN" },
  "wellfound": { label: "Wellfound (AI-стартапы, ML-вакансии)", dot: "lime", requires: null },
  "discord_dir": { label: "Discord-каталоги (disboard)", dot: "indigo", requires: null },
}

export const STREAM_COLLECTORS = new Set<string>(["certstream", "telegram"])

export const SETTINGS_DEFAULTS = {
  prefilter_en_strong: ["free credit", "free credits", "free trial", "free api", "free tier", "api trial", "no credit card", "no card required", "sign up free", "register for free", "free access", "free tokens", "free quota", "get free", "claim free", "free plan includes", "promo code", "coupon code", "discount code", "use code", "free pro", "pro for free", "pro plan free", "get it free", "access for free", "free with"],
  prefilter_en_weak: ["credits", "sign up", "signup", "register", "redeem", "promo", "referral", "invite", "api key", "trial", "$"],
  prefilter_ru: ["триал", "кредит", "бесплатн", "api ключ", "апи ключ", "регистрац", "раздач", "раздают", "баланс", "халяв", "промокод", "бонус"],
  prefilter_zh_strong: ["注册送", "公益站", "中转站", "免费api", "白嫖", "送额度", "送余额", "送刀", "免费额度", "注册即送", "新用户送"],
  prefilter_zh_weak: ["免费", "额度", "中转"],
  score_w_freshness: 0.4,
  score_w_amount: 0.3,
  score_w_ease: 0.2,
  score_w_reliability: 0.1,
  early_signal_boost: 0.1,
  discovery_limit: 40,
  notify_min_score: 0.6,
} as const
