"""End-to-end test for the discovery pipeline.

Proves the full path:  signal text → harvest domain → probe → promote service.

Uses a temporary SQLite DB and a mocked HTTP transport so the test is
deterministic and offline. Simulates the 4 real TG posts as off-hand mentions
that the prefilter would normally DROP — showing we still discover the domains.

Run:  python test_discovery.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile

# Point the app at a throwaway SQLite file BEFORE importing runtime.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["AIRADAR_PLATFORM"] = "local"
os.environ["AIRADAR_DB_URL"] = f"sqlite:///{_tmp.name}"

import httpx  # noqa: E402

from aiapiradar.core.signal import Signal  # noqa: E402
from aiapiradar.db import get_db, init_db  # noqa: E402
from aiapiradar.pipeline.pipeline import Pipeline  # noqa: E402

GREEN = "\033[92m"; RED = "\033[91m"; YELLOW = "\033[93m"; GREY = "\033[90m"; RESET = "\033[0m"
if sys.platform == "win32":
    os.system("")


# ── Fake sites the probe will "visit" ────────────────────────────────────────
# Mirrors what enrich.probe() fetches: GET https://{domain}/ and /pricing
FAKE_SITES = {
    "zenmux.ai": {
        "/": "<title>ZenMux — AI Model Routing</title> Access GLM, Kimi, DeepSeek via one API.",
        "/pricing": "Start with a free trial. No credit card required. $5 free credits for GLM and Claude.",
    },
    "getmerlin.in": {
        "/": "<title>Merlin AI</title> Chat with GPT, Claude, Gemini.",
        "/pricing": "Free trial available. Get free credits. Claude Opus and GPT included.",
    },
    "band.ai": {
        # No /pricing offer triggers → should NOT be promoted (proves we're conservative)
        "/": "<title>Band</title> Multi-agent orchestration infrastructure.",
        "/pricing": "Contact sales for enterprise plans.",
    },
}


def _mock_handler(request: httpx.Request) -> httpx.Response:
    host = request.url.host
    path = request.url.path or "/"
    site = FAKE_SITES.get(host)
    if site is None:
        return httpx.Response(404, text="not found")
    body = site.get(path)
    if body is None:
        return httpx.Response(404, text="no page")
    return httpx.Response(200, text=body)


# ── The 4 posts as low-signal mentions (would fail the offer classifier) ─────
POSTS = [
    Signal(source="forum_rss",
           raw_text="btw saw zenmux.ai today, looks like it has an AI API free trial",
           source_url="https://linux.do/t/123"),
    Signal(source="hackernews",
           raw_text="Anyone tried getmerlin.in? Heard the API gives free credits to new users.",
           source_url="https://news.ycombinator.com/item?id=1"),
    Signal(source="reddit",
           raw_text="band.ai is a cool AI agent platform, not sure about pricing though",
           source_url="https://reddit.com/r/x/2"),
    # A noise post with a domain but NO AI context → must NOT be harvested
    Signal(source="forum_rss",
           raw_text="my favorite pasta recipe is on cooking-blog.com, check it out",
           source_url="https://linux.do/t/999"),
]


def _check(label: str, ok: bool) -> bool:
    mark = f"{GREEN}✅{RESET}" if ok else f"{RED}❌{RESET}"
    print(f"  {mark}  {label}")
    return ok


async def main() -> None:
    init_db()

    print(f"\n{YELLOW}1) Run pipeline — harvest domains from low-signal mentions{RESET}")
    pipe = Pipeline()
    stats = pipe.process_signals(POSTS)
    print(f"  {GREY}pipeline stats: {stats}{RESET}")

    with get_db() as db:
        cands = {r["domain"]: r["status"]
                 for r in db.execute("SELECT domain, status FROM domain_candidates")}
    print(f"  {GREY}candidates: {cands}{RESET}")

    all_ok = True
    all_ok &= _check("zenmux.ai harvested", "zenmux.ai" in cands)
    all_ok &= _check("getmerlin.in harvested", "getmerlin.in" in cands)
    all_ok &= _check("band.ai harvested", "band.ai" in cands)
    all_ok &= _check("cooking-blog.com NOT harvested (no AI context)",
                     "cooking-blog.com" not in cands)

    print(f"\n{YELLOW}2) Run discovery worker — probe + promote (mocked HTTP){RESET}")
    # Patch the AsyncClient used by the discovery worker with our mock transport.
    import aiapiradar.discover as discover

    transport = httpx.MockTransport(_mock_handler)
    real_client = httpx.AsyncClient

    def _client_factory(*a, **kw):
        kw.pop("transport", None)
        return real_client(transport=transport, **{k: v for k, v in kw.items()
                                                   if k in ("timeout", "follow_redirects", "headers")})

    discover.httpx.AsyncClient = _client_factory  # type: ignore
    try:
        dstats = await discover.run_discovery(limit=40)
    finally:
        discover.httpx.AsyncClient = real_client  # type: ignore
    print(f"  {GREY}discovery stats: {dstats}{RESET}")

    with get_db() as db:
        services = {r["canonical_domain"]: r["status"]
                    for r in db.execute("SELECT canonical_domain, status FROM services")}
        cand_status = {r["domain"]: r["status"]
                       for r in db.execute("SELECT domain, status FROM domain_candidates")}
    print(f"  {GREY}services: {services}{RESET}")
    print(f"  {GREY}candidate status: {cand_status}{RESET}")

    all_ok &= _check("zenmux.ai PROMOTED to services (free trial on /pricing)",
                     "zenmux.ai" in services)
    all_ok &= _check("getmerlin.in PROMOTED to services (free credits on /pricing)",
                     "getmerlin.in" in services)
    all_ok &= _check("band.ai NOT promoted (no offer triggers — conservative)",
                     "band.ai" not in services)

    print()
    if all_ok:
        print(f"{GREEN}ALL CHECKS PASSED — we discover unknown sites from plain mentions.{RESET}")
    else:
        print(f"{RED}SOME CHECKS FAILED.{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    finally:
        try:
            os.unlink(_tmp.name)
        except OSError:
            pass
