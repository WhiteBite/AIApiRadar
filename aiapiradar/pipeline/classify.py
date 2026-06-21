"""Classification: turn raw text into a structured Offer description.

Two implementations behind one interface:
  - HeuristicClassifier: regex/keyword based, zero-cost, always available.
    Used for offline runs and tests, and as the LLM fallback.
  - LLMClassifier: OpenAI-compatible chat call returning strict JSON.

get_classifier() picks LLM when an API key is configured, else heuristic.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from pydantic import BaseModel, Field

from ..config import Settings, get_settings
from ..logging_conf import get_logger
from ..models import OFFER_TYPES
from . import prefilter

log = get_logger("classify")

_MODEL_KEYWORDS = [
    "claude", "opus", "sonnet", "haiku", "gpt", "o1", "o3", "gemini",
    "glm", "deepseek", "qwen", "mistral", "llama", "grok",
]
_AMOUNT_RES = [
    re.compile(r"\$\s?(\d+(?:[.,]\d+)?)"),
    re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:刀|美元)"),
    re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:баллов|кредит\w*|credits?)", re.IGNORECASE),
]
_REFERRAL_RE = re.compile(r"[?&](ref|invite|aff|promo|campaignId)=|referral|реф[- ]?ссылк|invite", re.IGNORECASE)


class Classification(BaseModel):
    is_offer: bool = False
    service_name: Optional[str] = None
    offer_type: str = "other"
    amount: Optional[float] = None
    currency: Optional[str] = None
    models: list[str] = Field(default_factory=list)
    claim_steps: Optional[str] = None
    requirements: Optional[str] = None
    referral_required: bool = False
    effort: Optional[str] = None   # "easy" / "medium" / "hard"
    unit: Optional[str] = None     # "usd" / "credits" / "days" / "months"
    confidence: float = 0.0

    @classmethod
    def not_offer(cls) -> "Classification":
        return cls(is_offer=False, confidence=0.0)


def _parse_amount(text: str) -> tuple[Optional[float], Optional[str]]:
    for rx in _AMOUNT_RES:
        m = rx.search(text)
        if m:
            val = float(m.group(1).replace(",", "."))
            currency = "USD" if rx is _AMOUNT_RES[0] or "刀" in text or "美元" in text else None
            return val, currency
    return None, None


def _find_models(text: str) -> list[str]:
    low = text.lower()
    return sorted({m for m in _MODEL_KEYWORDS if m in low})


def _guess_type(text: str, domains: list[str], lang: str) -> str:
    low = text.lower()
    if lang == "zh" or any(k in text for k in ("中转", "公益站", "注册送")):
        return "relay"
    if "huggingface" in low or "model release" in low or "релиз модел" in low:
        return "model_release"
    if ("star" in low or "звезд" in low) and ("github" in low or "репозитор" in low):
        return "grant"
    return "saas_trial"


_HARD_KEYWORDS = [
    "карта", "card", "b1n", "bin", "namso", "namso-gen", "генератор карт",
    "виртуальн", "vpn", "vps", "впн", "отменить", "cancel subscription",
    "пробный период", "refund", "fake card", "фейк", "chargeback",
]
_MEDIUM_KEYWORDS = [
    "ref=", "invite=", "реф-ссылк", "реферальн", "referral",
    "звезд", "github star", "star on github", "репозитор",
    "промокод", "promo code", "coupon", "business email", "бизнес почт",
    ".edu", "edu email",
]


def _detect_effort(text: str, referral_required: bool) -> str:
    low = text.lower()
    if any(k in low for k in _HARD_KEYWORDS):
        return "hard"
    if referral_required or any(k in low for k in _MEDIUM_KEYWORDS):
        return "medium"
    return "easy"


def _detect_unit(text: str, amount: Optional[float], currency: Optional[str]) -> Optional[str]:
    """Detect what unit the amount represents."""
    if not amount:
        return None
    if currency == "USD":
        return "usd"
    low = text.lower()
    if re.search(r'\d+\s*(?:кредит|credit|балл|баллов|points?|cr\b)', low):
        return "credits"
    if re.search(r'\d+\s*(?:дн|day|суток)', low):
        return "days"
    if re.search(r'\d+\s*(?:месяц|month|мес\b)', low):
        return "months"
    return "usd" if currency else "credits"


class HeuristicClassifier:
    name = "heuristic"

    def classify(self, text: str, url: Optional[str], lang: str, domains: list[str]) -> Classification:
        matched, hits = prefilter.match(text)
        if not matched:
            return Classification.not_offer()
        amount, currency = _parse_amount(text)
        models = _find_models(text)
        referral = bool(_REFERRAL_RE.search(text)) or bool(url and _REFERRAL_RE.search(url))
        confidence = 0.45
        if amount:
            confidence += 0.25
        if models:
            confidence += 0.15
        name = domains[0] if domains else None
        effort = _detect_effort(text, referral)
        unit = _detect_unit(text, amount, currency)
        return Classification(
            is_offer=True,
            service_name=name,
            offer_type=_guess_type(text, domains, lang),
            amount=amount,
            currency=currency,
            models=models,
            referral_required=referral,
            effort=effort,
            unit=unit,
            confidence=min(confidence, 0.95),
        )

    def classify_batch(self, items: list[tuple], batch_size: int = 15) -> list["Classification"]:
        """Uniform interface with LLMClassifier; just maps classify() per item."""
        return [self.classify(text, url, lang, domains) for (text, url, lang, domains) in items]


_LLM_SCHEMA = (
    '{"is_offer": bool, "service_name": str|null, "offer_type": one of '
    f"{list(OFFER_TYPES)}, "
    '"amount": number|null, "currency": str|null, "models": [str], '
    '"claim_steps": str|null, "requirements": str|null, '
    '"referral_required": bool, '
    '"effort": "easy"|"medium"|"hard", "unit": "usd"|"credits"|"days"|"months"|null, '
    '"confidence": number 0..1}'
)
_LLM_RULES = (
    "Rules for effort: easy=just signup with email; medium=need referral/promo code/GitHub star/business email; "
    "hard=requires fake card/VPN/subscription cancellation/automation. "
    "If the message is not about obtaining free/credited AI access, set is_offer=false."
)
_LLM_SYSTEM = (
    "You classify messages about FREE AI API credits / trials. "
    "Return STRICT JSON only, matching this schema: " + _LLM_SCHEMA + ". " + _LLM_RULES
)
_LLM_BATCH_SYSTEM = (
    "You classify messages about FREE AI API credits / trials. "
    "You receive a JSON array of items, each with an integer 'id' and a 'text'. "
    "Return STRICT JSON only of the form "
    '{"results": [{"id": <same id>, ...fields...}]} '
    "with exactly one result object per input id (preserve the ids). "
    "Each result's fields match this schema: " + _LLM_SCHEMA + ". " + _LLM_RULES
)


def _coerce_classification(data: dict) -> Classification:
    """Validate/normalize a raw LLM dict into a Classification."""
    if data.get("offer_type") not in OFFER_TYPES:
        data["offer_type"] = "other"
    if data.get("effort") not in ("easy", "medium", "hard"):
        data["effort"] = None
    if data.get("unit") not in ("usd", "credits", "days", "months"):
        data["unit"] = None
    data.pop("id", None)  # strip batch index if present
    return Classification(**data)


class LLMClassifier:
    name = "llm"

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._fallback = HeuristicClassifier()
        self._client = None
        # models to try, in order; ones that hit a daily quota get parked here
        self._models = list(self.settings.llm_model_chain)
        self._exhausted: set[str] = set()

    def _client_lazy(self):
        if self._client is None:
            from openai import OpenAI  # lazy: only needed when LLM is enabled

            self._client = OpenAI(
                base_url=self.settings.llm_base_url,
                api_key=self.settings.llm_api_key,
            )
        return self._client

    def _live_models(self) -> list[str]:
        live = [m for m in self._models if m not in self._exhausted]
        return live or list(self._models)  # if all parked, retry from scratch

    @staticmethod
    def _is_quota_error(exc: Exception) -> bool:
        from openai import RateLimitError

        if isinstance(exc, RateLimitError):
            return True
        msg = str(exc).lower()
        return "429" in msg or "quota" in msg or "resource_exhausted" in msg

    def _complete(self, system: str, user: str) -> str:
        """Run one chat completion, rotating models when one hits its quota.

        Returns the raw JSON string content. Raises if every model is
        exhausted so the caller can fall back to the heuristic.
        """
        client = self._client_lazy()
        last_exc: Optional[Exception] = None
        for model in self._live_models():
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0,
                )
                return resp.choices[0].message.content
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if self._is_quota_error(exc):
                    self._exhausted.add(model)
                    log.warning("model %s hit quota/429; rotating to next", model)
                    continue
                raise
        raise last_exc or RuntimeError("no LLM models available")

    def classify(self, text: str, url: Optional[str], lang: str, domains: list[str]) -> Classification:
        # cheap gate first: don't spend tokens on obvious noise
        matched, _ = prefilter.match(text)
        if not matched:
            return Classification.not_offer()
        try:
            user = f"URL: {url or (domains[0] if domains else 'unknown')}\nTEXT:\n{text[:4000]}"
            content = self._complete(_LLM_SYSTEM, user)
            data = json.loads(content)
            return _coerce_classification(data)
        except Exception:
            log.exception("LLM classify failed; using heuristic fallback")
            return self._fallback.classify(text, url, lang, domains)

    def classify_batch(self, items: list[tuple], batch_size: int = 15) -> list[Classification]:
        """Classify many items in few LLM calls to fit tight rate/daily quotas.

        items: list of (text, url, lang, domains) tuples.
        Returns a Classification per item, in the same order. Items that fail
        the cheap prefilter are not sent to the LLM (returned as not_offer).
        On quota errors the model rotates; if all models are exhausted (or a
        batch errors) the affected items fall back to the heuristic classifier.
        """
        results: list[Optional[Classification]] = [None] * len(items)
        # cheap gate: collect indices worth sending
        pending: list[int] = []
        for i, (text, _url, _lang, _domains) in enumerate(items):
            matched, _ = prefilter.match(text)
            if matched:
                pending.append(i)
            else:
                results[i] = Classification.not_offer()

        for start in range(0, len(pending), batch_size):
            chunk = pending[start:start + batch_size]
            payload = []
            for idx in chunk:
                text, url, _lang, domains = items[idx]
                payload.append({
                    "id": idx,
                    "url": url or (domains[0] if domains else "unknown"),
                    "text": text[:3000],
                })
            try:
                content = self._complete(
                    _LLM_BATCH_SYSTEM, json.dumps(payload, ensure_ascii=False)
                )
                data = json.loads(content)
                rows = data.get("results", data if isinstance(data, list) else [])
                by_id: dict[int, dict] = {}
                for row in rows:
                    if isinstance(row, dict) and "id" in row:
                        try:
                            by_id[int(row["id"])] = row
                        except (TypeError, ValueError):
                            continue
                for idx in chunk:
                    row = by_id.get(idx)
                    if row is not None:
                        try:
                            results[idx] = _coerce_classification(dict(row))
                            continue
                        except Exception:
                            log.warning("batch row coerce failed for id=%s", idx)
                    # missing/invalid row -> heuristic fallback
                    text, url, lang, domains = items[idx]
                    results[idx] = self._fallback.classify(text, url, lang, domains)
            except Exception:
                log.exception("LLM batch classify failed; heuristic fallback for chunk")
                for idx in chunk:
                    text, url, lang, domains = items[idx]
                    results[idx] = self._fallback.classify(text, url, lang, domains)

        return [r if r is not None else Classification.not_offer() for r in results]


def get_classifier(settings: Optional[Settings] = None):
    settings = settings or get_settings()
    if settings.has_llm:
        return LLMClassifier(settings)
    return HeuristicClassifier()
