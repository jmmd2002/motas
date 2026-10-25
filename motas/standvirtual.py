"""Standvirtual (OLX Group) listing source.

Standvirtual is where OLX Portugal's motorcycle listings live; most ads are
mirrored to olx.pt ("export_olx"). Pages embed their data as Next.js JSON
(__NEXT_DATA__), which is far more stable than scraping HTML. Only paths that
robots.txt allows are requested (search and ad pages, not /api/).
"""

import json
import re
import time
from datetime import datetime

import requests

from .text import html_to_text

BASE = "https://www.standvirtual.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
    "Accept-Language": "pt-PT,pt;q=0.9",
}
REQUEST_DELAY_S = 2.0
MAX_PAGES = 20

_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)


class SourceError(RuntimeError):
    pass


class Fetcher:
    """HTTP client that keeps a polite gap between requests."""

    def __init__(self, delay: float = REQUEST_DELAY_S, session: requests.Session | None = None):
        self.delay = delay
        self.session = session or requests.Session()
        self.session.headers.update(HEADERS)
        self._last = 0.0

    def get(self, url: str) -> str | None:
        """Return the page HTML, or None if the page no longer exists."""
        wait = self._last + self.delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        try:
            r = self.session.get(url, timeout=30)
        finally:
            self._last = time.monotonic()
        if r.status_code in (404, 410):
            return None
        if r.status_code != 200:
            raise SourceError(f"{url} returned HTTP {r.status_code}")
        return r.text


def next_data(page: str) -> dict:
    m = _NEXT_DATA.search(page)
    if not m:
        raise SourceError("page has no __NEXT_DATA__ block (layout changed?)")
    return json.loads(m.group(1))


# --- search pages ---------------------------------------------------------

def parse_search(page: str) -> tuple[int, list[dict]]:
    """Return (total result count, advert nodes) from a search page."""
    state = next_data(page)["props"]["pageProps"].get("urqlState") or {}
    for entry in state.values():
        data = json.loads(entry.get("data") or "{}")
        if "advertSearch" in data:
            s = data["advertSearch"]
            return s["totalCount"], [e["node"] for e in s["edges"]]
    raise SourceError("search page has no advertSearch result")


def search(fetcher: Fetcher, path: str) -> list[dict]:
    """All advert nodes for a search path, across pages."""
    nodes: dict[str, dict] = {}
    for page_no in range(1, MAX_PAGES + 1):
        page = fetcher.get(f"{BASE}{path}?page={page_no}")
        if page is None:
            break
        total, batch = parse_search(page)
        new = [n for n in batch if n["id"] not in nodes]
        nodes.update((n["id"], n) for n in new)
        if not new or len(nodes) >= total:
            break
    return list(nodes.values())


def node_summary(node: dict) -> dict:
    """The fields of a search-result node needed to pre-select candidates."""
    params = {p["key"]: p["value"] for p in node.get("parameters", [])}
    return {
        "id": node["id"],
        "url": node["url"],
        "title": node.get("title") or "",
        "model": params.get("model"),
        "version": params.get("version") or "",
        "cc": _int(params.get("engine_capacity")),
        "badges": node.get("badges") or [],
    }


# --- ad pages -------------------------------------------------------------

def _int(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _param(params: dict, key: str) -> str | None:
    values = (params.get(key) or {}).get("values") or []
    return values[0]["value"] if values else None


def _bool_param(params: dict, key: str) -> bool | None:
    v = _param(params, key)
    return None if v is None else v == "1"


def _iso(s: str | None) -> str | None:
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00")).isoformat()


def parse_ad(page: str) -> dict | None:
    """Normalised listing from an ad page, or None if the ad is not active."""
    ad = next_data(page)["props"]["pageProps"].get("advert")
    if not ad or ad.get("status") != "ACTIVE":
        return None
    params = ad.get("parametersDict") or {}
    price = ad.get("price") or {}
    seller = ad.get("seller") or {}
    loc = seller.get("location") or {}
    coords = loc.get("map") or {}
    photos = (ad.get("images") or {}).get("photos") or []
    features = [v["label"] for v in (params.get("features") or {}).get("values", [])]

    return {
        "id": str(ad["id"]),
        "url": ad["url"],
        "title": ad.get("title") or "",
        "model": _param(params, "model"),
        "version": _param(params, "version") or "",
        "price": _int(price.get("value")),
        "negotiable": "ad-page-negotiable-tag" in (price.get("labels") or []),
        "km": _int(_param(params, "mileage")),
        "reg_year": _int(_param(params, "first_registration_year")),
        "reg_month": _int(_param(params, "first_registration_month")),
        "power_cv": _int(_param(params, "engine_power")),
        "cc": _int(_param(params, "engine_capacity")),
        "owners": _int(_param(params, "number_of_registrations")),
        "service_book": _bool_param(params, "complete_review_book"),
        "second_key": _bool_param(params, "second_key"),
        "origin": _param(params, "origin"),
        "condition": _param(params, "new_used"),
        "is_parts": bool(ad.get("isParts")),
        "seller_type": "private" if seller.get("type") == "PRIVATE" else "professional",
        "seller_name": seller.get("name"),
        "region": loc.get("region"),
        "city": loc.get("city"),
        "lat": coords.get("latitude"),
        "lon": coords.get("longitude"),
        "features": features,
        "description": html_to_text(ad.get("description") or ""),
        "photo_url": photos[0]["url"] + ";s=640x480" if photos else None,
        "photo_count": len(photos),
        "listed_at": _iso(ad.get("originalCreatedAt") or ad.get("createdAt")),
    }
