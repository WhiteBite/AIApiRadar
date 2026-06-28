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

# Allowed risk-flag vocabulary for the structured `conditions` object.
_RISK_FLAGS = ("vpn", "fake_card", "cancel_subscription", "chargeback", "referral")


def _default_conditions() -> dict:
    """Return a fresh default `conditions` object (all keys, safe defaults)."""
    return {
        "requires_card": False,
        "requires_phone": False,
        "new_users_only": False,
        "region": None,
        "risk_flags": [],
    }


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
    conditions: dict = Field(default_factory=dict)
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


# Local keyword lists for structured `conditions` heuristics (no external calls).
_CARD_KEYWORDS = [
    "credit card", "debit card", "debit", "card required", "card", "карта",
    "карту", "картой", "виза", "visa", "mastercard", "信用卡", "银行卡", "绑卡",
]
_PHONE_KEYWORDS = [
    "phone verification", "phone number", "phone", "sms", "verify by sms",
    "телефон", "смс", "номер телефона", "手机", "短信", "手机号", "手机验证",
]
_NEW_USER_KEYWORDS = [
    "new users", "new user", "new account", "new accounts", "first deposit",
    "только новые", "новым пользоват", "新用户", "首充", "首次充值", "新注册",
]
# Explicit "no card needed" phrasing — a POSITIVE signal (cardless), not a
# requirement. Checked before _CARD_KEYWORDS so "no credit card" isn't misread
# as "requires card" by the naive substring match.
_NO_CARD_RE = re.compile(
    r"no\s+(?:credit\s+|debit\s+)?card|without\s+(?:a\s+)?card|no\s+cc\b|"
    r"card[-\s]?free|no\s+payment\s+(?:method|required)|"
    r"без\s+карт|не\s+(?:нужн\w*|требу\w*|надо)\s+карт|"
    r"无需(?:信用卡|绑卡)|不需要(?:信用卡|绑卡)|免绑卡|免信用卡",
    re.IGNORECASE,
)


def _detect_conditions(text: str, url: Optional[str], referral_required: bool) -> dict:
    """Best-effort structured conditions from text, reusing existing keyword lists.

    Pure local string matching — no external calls. Returns the strict
    `conditions` object (see _default_conditions()).
    """
    cond = _default_conditions()
    low = text.lower()
    blob = low + (" " + url.lower() if url else "")

    # 3-state: assert only what we detect. Explicit "no card" → False (a
    # positive selling point); a card keyword → True; neither → unknown (omit
    # the key so the UI shows no chip rather than a misleading one).
    if _NO_CARD_RE.search(blob):
        cond["requires_card"] = False
    elif any(k in low for k in _CARD_KEYWORDS):
        cond["requires_card"] = True
    else:
        cond.pop("requires_card", None)

    if any(k in low for k in _PHONE_KEYWORDS):
        cond["requires_phone"] = True
    else:
        cond.pop("requires_phone", None)

    if any(k in low for k in _NEW_USER_KEYWORDS):
        cond["new_users_only"] = True
    else:
        cond.pop("new_users_only", None)

    # Region: simple best-effort tags.
    region = None
    if "us only" in low or "us-only" in low or "сша только" in low:
        region = "US-only"
    elif "eu only" in low or "eu-only" in low:
        region = "EU-only"
    elif "cn only" in low or "cn-only" in low or "china only" in low:
        region = "CN-only"
    elif "region" in low or "only available in" in low:
        region = "region-restricted"
    cond["region"] = region

    # Risk flags: map detected hard/medium keywords → controlled vocabulary.
    flags: list[str] = []
    if "vpn" in low or "впн" in low:
        flags.append("vpn")
    if any(k in low for k in ("fake card", "namso", "bin", "b1n", "генератор карт", "виртуальн")):
        flags.append("fake_card")
    if any(k in low for k in ("cancel subscription", "отменить", "cancel the subscription")):
        flags.append("cancel_subscription")
    if "chargeback" in low or "refund" in low or "возврат" in low:
        flags.append("chargeback")
    if referral_required or any(k in blob for k in ("referral", "ref=", "invite", "реф")):
        flags.append("referral")
    # dedupe, keep only allowed flags, preserve order
    seen: set[str] = set()
    cond["risk_flags"] = [f for f in flags if f in _RISK_FLAGS and not (f in seen or seen.add(f))]
    return cond


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
        cond = _detect_conditions(text, url, referral)
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
            conditions=cond,
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
    '"conditions": {"requires_card": bool, "requires_phone": bool, '
    '"new_users_only": bool, "region": str|null, '
    '"risk_flags": [subset of "vpn"|"fake_card"|"cancel_subscription"|"chargeback"|"referral"]}, '
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
    data["conditions"] = _coerce_conditions(data.get("conditions"))
    data.pop("id", None)  # strip batch index if present
    return Classification(**data)


def _coerce_conditions(raw) -> dict:
    """Validate/normalize a raw `conditions` value into the strict object.

    Missing/invalid input yields the safe default dict. Each key is coerced to
    its declared type; unknown risk flags are dropped.
    """
    cond = _default_conditions()
    if not isinstance(raw, dict):
        return cond
    for key in ("requires_card", "requires_phone", "new_users_only"):
        if key in raw:
            cond[key] = bool(raw[key])
    region = raw.get("region")
    cond["region"] = str(region) if isinstance(region, str) and region.strip() else None
    flags = raw.get("risk_flags")
    if isinstance(flags, (list, tuple)):
        cond["risk_flags"] = [
            str(f) for f in flags if isinstance(f, str) and f in _RISK_FLAGS
        ]
    return cond


class LLMClassifier:
    name = "llm"

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._fallback = HeuristicClassifier()
        # Ordered provider list from config. Each entry is a dict:
        #   {"name": str, "base_url": str, "api_key": str, "models": list[str]}
        # Only providers with a usable key+base_url are present (see config).
        self._providers: list[dict] = list(self.settings.llm_providers)
        # Lazy per-provider OpenAI client cache, keyed by provider name. We
        # build a client only when a provider is actually reached.
        self._clients: dict[str, object] = {}
        # Parked (provider_name, model) pairs that hit a daily quota / 429.
        self._exhausted: set[tuple[str, str]] = set()

    def _client_for(self, provider: dict):
        """Lazily create and cache the OpenAI client for one provider.

        Each provider gets its own base_url + api_key, so they cannot share a
        single client. Cached by provider name to avoid re-creating it.
        """
        name = provider["name"]
        client = self._clients.get(name)
        if client is None:
            from openai import OpenAI  # lazy: only needed when LLM is enabled

            client = OpenAI(
                base_url=provider["base_url"],
                api_key=provider["api_key"],
            )
            self._clients[name] = client
        return client

    def _live_pairs(self) -> list[tuple[dict, str]]:
        """(provider, model) pairs to try, in priority order.

        Walks providers in order and, within each, its models in order, while
        skipping pairs already parked as exhausted. If every pair is parked,
        retry from the full list once — this tolerates transient daily-quota
        windows (mirrors the previous _live_models "retry from scratch").
        """
        all_pairs: list[tuple[dict, str]] = []
        live: list[tuple[dict, str]] = []
        for provider in self._providers:
            for model in provider.get("models", []):
                all_pairs.append((provider, model))
                if (provider["name"], model) not in self._exhausted:
                    live.append((provider, model))
        return live or all_pairs

    @staticmethod
    def _is_quota_error(exc: Exception) -> bool:
        from openai import RateLimitError

        if isinstance(exc, RateLimitError):
            return True
        msg = str(exc).lower()
        return "429" in msg or "quota" in msg or "resource_exhausted" in msg

    def _complete(self, system: str, user: str) -> str:
        """Run one chat completion with provider→model fallback.

        Tries each provider in priority order and, within a provider, each of
        its models. On a quota/429 error the offending (provider, model) pair
        is parked and we move on; on any OTHER error we log a warning and also
        move on, so a single misbehaving provider can't sink the whole run.
        Returns the raw JSON string content. Raises when every provider+model
        is exhausted/failed so the caller falls back to the heuristic.
        """
        last_exc: Optional[Exception] = None
        for provider, model in self._live_pairs():
            pname = provider["name"]
            try:
                client = self._client_for(provider)
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
                    self._exhausted.add((pname, model))
                    log.warning(
                        "provider %s model %s hit quota/429; rotating to next",
                        pname, model,
                    )
                else:
                    log.warning(
                        "provider %s model %s failed (%s); rotating to next",
                        pname, model, exc,
                    )
                continue
        raise last_exc or RuntimeError("no LLM providers available")

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
