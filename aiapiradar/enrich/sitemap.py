"""robots.txt / sitemap.xml discovery crawl helpers.

Last-resort offer discovery: when the fixed offer-path sweep finds nothing,
mine robots.txt + sitemap.xml for offer-bearing URLs at non-standard paths.
"""
from __future__ import annotations

import re

import httpx

# Path keywords that mark a URL (from robots.txt / sitemap.xml) as offer-bearing.
_OFFER_URL_RE = re.compile(
    r"pricing|plans|billing|subscribe|redeem|promo|coupon|trial|credits|free",
    re.IGNORECASE,
)
_SITEMAP_LOC_RE = re.compile(r"<loc>\s*(.*?)\s*</loc>", re.IGNORECASE | re.DOTALL)


async def _discover_offer_urls(domain: str, client: httpx.AsyncClient,
                               budget: "_ReqBudget | None" = None) -> list[str]:
    """Crawl robots.txt + sitemap.xml to find offer-bearing URLs.

    Used as a last resort when the fixed OFFER_PATHS sweep found no pricing
    triggers — e.g. a site whose offer lives at a non-standard path that's only
    discoverable via its sitemap. Returns absolute URLs whose path matches an
    offer keyword (pricing/plans/billing/redeem/trial/credits/free/…), capped at
    5. Fully guarded: any failure (missing robots, 404 sitemap, bad XML) yields
    an empty/short list and never raises.
    """
    def _take() -> bool:
        return budget.take() if budget is not None else True

    sitemaps: list[str] = []

    # robots.txt → collect any "Sitemap:" directives.
    if _take():
        try:
            r = await client.get(f"https://{domain}/robots.txt")
            if r.status_code == 200:
                for line in (r.text or "").splitlines():
                    line = line.strip()
                    if line.lower().startswith("sitemap:"):
                        sm = line.split(":", 1)[1].strip()
                        if sm:
                            sitemaps.append(sm)
        except Exception:
            pass

    # Always also try the conventional sitemap location.
    sitemaps.append(f"https://{domain}/sitemap.xml")

    locs: list[str] = []
    seen: set[str] = set()
    for sm in sitemaps:
        if sm in seen:
            continue
        seen.add(sm)
        if not _take():
            break
        try:
            r = await client.get(sm)
            if r.status_code == 200:
                for m in _SITEMAP_LOC_RE.finditer(r.text or ""):
                    loc = m.group(1).strip()
                    if loc:
                        locs.append(loc)
        except Exception:
            continue

    out: list[str] = []
    for loc in locs:
        try:
            path = httpx.URL(loc).path or ""
        except Exception:
            path = loc
        if _OFFER_URL_RE.search(path) and loc not in out:
            out.append(loc)
            if len(out) >= 5:
                break
    return out
