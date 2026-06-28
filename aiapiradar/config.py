"""Application configuration loaded from environment / .env.

All settings are prefixed with AIRADAR_ to avoid collisions.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AIRADAR_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Storage
    db_url: str = "sqlite:///./aiapiradar.db"

    # Logging
    log_level: str = "INFO"

    # LLM classifier (OpenAI-compatible client)
    llm_provider: str = "openai"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"
    llm_api_key: str = ""
    # Comma-separated models tried in order when the primary hits a 429/quota.
    # Each Gemini free-tier model has its OWN daily quota, so rotating across
    # them multiplies effective daily capacity.
    llm_fallback_models: str = ""
    # Extra free LLM providers (all OpenAI-compatible). Empty key = provider skipped.
    groq_api_key: str = ""
    gemini_api_key: str = ""
    mistral_api_key: str = ""
    cerebras_api_key: str = ""
    openrouter_api_key: str = ""
    # Per-provider default model (override via env if a provider changes its lineup).
    groq_model: str = "llama-3.3-70b-versatile"
    gemini_model: str = "gemini-2.0-flash"
    mistral_model: str = "mistral-small-latest"
    cerebras_model: str = "llama-3.3-70b"
    openrouter_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    # Cloudflare Workers AI — zero-setup backstop provider. Reuses the CF
    # account id + api token already configured for D1 (no extra signup). Free
    # ~10k neurons/day. OpenAI-compatible endpoint.
    workersai_model: str = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    # Ordered provider priority (csv). "legacy" = the llm_base_url/llm_model/llm_api_key triple.
    # workersai is last → free floor tried after external providers, before heuristic.
    llm_provider_order: str = "legacy,gemini,groq,mistral,cerebras,openrouter,workersai"

    # Collector API keys (optional; collectors degrade gracefully if absent)
    github_token: str = ""
    search_api_key: str = ""
    search_cx: str = ""
    youtube_api_key: str = ""
    # Product Hunt developer token (optional; enables ph_upcoming collector).
    # Free token at https://www.producthunt.com/v2/oauth/applications.
    ph_token: str = ""

    # Telegram ingest (Telethon user client; optional)
    tg_api_id: int = 0
    tg_api_hash: str = ""
    tg_session: str = "aiapiradar"

    # Twitter / X (optional; enables keyword search in TwitterCollector)
    # Get a free Bearer Token at developer.twitter.com → Free tier is enough.
    tw_bearer_token: str = ""

    # FOFA (optional; enables favicon-hash relay discovery in FofaCollector)
    # Get credentials at https://fofa.info → free tier has tiny quotas.
    fofa_key: str = ""
    fofa_email: str = ""

    # Scoring weights
    score_w_freshness: float = 0.4
    score_w_amount: float = 0.3
    score_w_ease: float = 0.2
    score_w_reliability: float = 0.1

    # Notifier
    tg_bot_token: str = ""
    tg_chat_id: str = ""
    notify_min_score: float = 0.6
    # Minimum offer confidence (max over its signals) for the "looks legit"
    # gate in group mode. Offers from other telegram channels bypass it.
    notify_min_confidence: float = 0.5

    # ── Telegram group (forum) routing ─────────────────────────────────────
    # When tg_group_chat_id is set, the notifier posts into forum TOPICS of
    # this supergroup instead of the single tg_chat_id feed. The bot must be an
    # admin with "Manage topics" rights and the group must have Topics enabled.
    # Format: a -100… supergroup id.
    tg_group_chat_id: str = ""
    # Explicit forum topic (message_thread_id) overrides. 0 = auto-create the
    # topic on first run and persist its id (see `cli tg-setup`).
    tg_topic_ai_services: int = 0   # 🤖 ИИ-сервисы и агенты
    tg_topic_freebies: int = 0      # 🎁 Халява и акции (VDS, кредиты, триалы)
    tg_topic_forwarded: int = 0     # 📡 Из других каналов

    # ── Platform selection ─────────────────────────────────────────────────
    # local       → SQLite/Postgres + APScheduler + FastAPI  (VPS / Docker)
    # cloudflare  → D1 REST API + Cron Workers               (CF free tier)
    platform: str = "local"

    # Cloudflare D1 credentials (only needed when platform=cloudflare)
    cf_account_id: str = ""
    cf_d1_database_id: str = ""
    cf_api_token: str = ""

    # RSSHub instance for Chinese social platform feeds (Bilibili, Zhihu, etc.)
    # Use a self-hosted instance to avoid rate-limits on the public one.
    rsshub_url: str = "https://rsshub.app"

    # ── Runner / execution ─────────────────────────────────────────────────
    # Selects HOW the application runs collectors + maintenance:
    #   process → long-lived APScheduler loop (VDS / Docker).
    #   batch   → single one-shot pass, no scheduler (serverless / CI cron).
    #   auto    → pick by `platform` (local→process, cloudflare→batch).
    runner: str = "auto"            # auto | process | batch  (auto → by platform)
    enable_discovery: bool = True   # gate the discovery worker on/off
    enable_streaming: bool = True   # ignored on non-VDS runners (batch never streams)
    discovery_limit: int = 40       # max domain candidates probed per discovery run
    probe_timeout: float = 15.0     # per-probe HTTP timeout (seconds)
    max_subrequests: int = 0        # 0 = unlimited (VDS); >0 caps outbound (serverless)

    @property
    def has_llm(self) -> bool:
        return len(self.llm_providers) > 0

    @property
    def llm_model_chain(self) -> list[str]:
        """Primary model first, then any fallbacks (deduped, order preserved)."""
        chain = [self.llm_model]
        for m in self.llm_fallback_models.split(","):
            m = m.strip()
            if m and m not in chain:
                chain.append(m)
        return chain

    @property
    def llm_providers(self) -> list[dict]:
        """Ordered, ready-to-use LLM providers.

        Each item: {"name": str, "base_url": str, "api_key": str, "models": list[str]}.
        Only providers whose api_key AND base_url are set are included. Order
        follows llm_provider_order. "legacy" maps to the llm_base_url/llm_model/
        llm_api_key triple (with llm_fallback_models as extra models).
        """
        catalog = {
            "legacy": (self.llm_base_url, self.llm_api_key, self.llm_model_chain),
            "gemini": ("https://generativelanguage.googleapis.com/v1beta/openai/", self.gemini_api_key, [self.gemini_model]),
            "groq": ("https://api.groq.com/openai/v1", self.groq_api_key, [self.groq_model]),
            "mistral": ("https://api.mistral.ai/v1", self.mistral_api_key, [self.mistral_model]),
            "cerebras": ("https://api.cerebras.ai/v1", self.cerebras_api_key, [self.cerebras_model]),
            "openrouter": ("https://openrouter.ai/api/v1", self.openrouter_api_key, [self.openrouter_model]),
            # Workers AI: base_url needs the CF account id; left "" (skipped) when
            # unset so the provider is only active with both account id + token.
            "workersai": (
                (f"https://api.cloudflare.com/client/v4/accounts/{self.cf_account_id}/ai/v1"
                 if self.cf_account_id else ""),
                self.cf_api_token,
                [self.workersai_model],
            ),
        }
        out: list[dict] = []
        for name in [x.strip() for x in self.llm_provider_order.split(",") if x.strip()]:
            entry = catalog.get(name)
            if not entry:
                continue
            base_url, api_key, models = entry
            if api_key and base_url:
                out.append({"name": name, "base_url": base_url, "api_key": api_key, "models": list(models)})
        return out

    @property
    def is_cloudflare(self) -> bool:
        return self.platform.lower() == "cloudflare"


@lru_cache
def get_settings() -> Settings:
    return Settings()
