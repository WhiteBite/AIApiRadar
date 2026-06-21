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

    # Collector API keys (optional; collectors degrade gracefully if absent)
    github_token: str = ""
    search_api_key: str = ""
    search_cx: str = ""
    youtube_api_key: str = ""

    # Telegram ingest (Telethon user client; optional)
    tg_api_id: int = 0
    tg_api_hash: str = ""
    tg_session: str = "aiapiradar"

    # Twitter / X (optional; enables keyword search in TwitterCollector)
    # Get a free Bearer Token at developer.twitter.com → Free tier is enough.
    tw_bearer_token: str = ""

    # Scoring weights
    score_w_freshness: float = 0.4
    score_w_amount: float = 0.3
    score_w_ease: float = 0.2
    score_w_reliability: float = 0.1

    # Notifier
    tg_bot_token: str = ""
    tg_chat_id: str = ""
    notify_min_score: float = 0.6

    # ── Platform selection ─────────────────────────────────────────────────
    # local       → SQLite/Postgres + APScheduler + FastAPI  (VPS / Docker)
    # cloudflare  → D1 REST API + Cron Workers               (CF free tier)
    platform: str = "local"

    # Cloudflare D1 credentials (only needed when platform=cloudflare)
    cf_account_id: str = ""
    cf_d1_database_id: str = ""
    cf_api_token: str = ""

    @property
    def has_llm(self) -> bool:
        return bool(self.llm_api_key)

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
    def is_cloudflare(self) -> bool:
        return self.platform.lower() == "cloudflare"


@lru_cache
def get_settings() -> Settings:
    return Settings()
