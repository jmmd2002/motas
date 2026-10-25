import json

import pytest

from motas import standvirtual


def page(next_data: dict) -> str:
    return (f'<html><script id="__NEXT_DATA__" type="application/json">'
            f'{json.dumps(next_data)}</script></html>')


def ad_page(**overrides) -> str:
    ad = {
        "id": "8097710938", "status": "ACTIVE", "title": "Honda CB CB500XA",
        "url": "https://www.standvirtual.com/motos/anuncio/x.html",
        "images": {"photos": [{"url": "https://img/1/image"}, {"url": "https://img/2/image"}]},
        "price": {"value": "5500", "currency": "EUR", "labels": ["ad-page-negotiable-tag"]},
        "description": "<p>Vendo <b>CB500XA</b></p><ul><li>Malas</li></ul>",
        "seller": {"type": "PRIVATE", "name": "Ana",
                   "location": {"city": "Viseu", "region": "Viseu",
                                "map": {"latitude": 40.6, "longitude": -7.9}}},
        "isParts": False,
        "originalCreatedAt": "2026-10-10T21:39:50Z", "createdAt": "2026-10-20T21:43:00Z",
        "parametersDict": {
            "model": {"values": [{"value": "cb"}]},
            "version": {"values": [{"value": "CB500XA"}]},
            "mileage": {"values": [{"value": "19093"}]},
            "first_registration_year": {"values": [{"value": "2020"}]},
            "first_registration_month": {"values": [{"value": "7"}]},
            "engine_capacity": {"values": [{"value": "471"}]},
            "number_of_registrations": {"values": [{"value": "2"}]},
            "complete_review_book": {"values": [{"value": "0"}]},
            "second_key": {"values": [{"value": "1"}]},
            "origin": {"values": [{"value": "national"}]},
            "new_used": {"values": [{"value": "used"}]},
            "features": {"values": [{"value": "abs", "label": "ABS"},
                                    {"value": "bags", "label": "Malas"}]},
        },
    }
    ad.update(overrides)
    return page({"props": {"pageProps": {"advert": ad}}})


def test_parse_ad():
    l = standvirtual.parse_ad(ad_page())
    assert l["id"] == "8097710938"
    assert (l["price"], l["km"], l["reg_year"], l["reg_month"], l["cc"]) == (5500, 19093, 2020, 7, 471)
    assert l["negotiable"] is True
    assert l["owners"] == 2
    assert l["service_book"] is False and l["second_key"] is True
    assert l["seller_type"] == "private"
    assert (l["lat"], l["lon"]) == (40.6, -7.9)
    assert l["features"] == ["ABS", "Malas"]
    assert l["description"] == "Vendo CB500XA\n• Malas"
    assert l["photo_count"] == 2 and l["photo_url"].endswith(";s=640x480")
    assert l["listed_at"].startswith("2026-10-10T21:39:50")
    assert l["power_cv"] is None


def test_inactive_ad_is_skipped():
    assert standvirtual.parse_ad(ad_page(status="REMOVED_BY_USER")) is None


def test_parse_search():
    search = {"advertSearch": {"totalCount": 2, "edges": [{"node": {"id": "1"}}, {"node": {"id": "2"}}]}}
    html = page({"props": {"pageProps": {"urqlState": {
        "a": {"data": json.dumps({"seoMetadata": {}})},
        "b": {"data": json.dumps(search)},
    }}}})
    assert standvirtual.parse_search(html) == (2, [{"id": "1"}, {"id": "2"}])


def test_layout_change_is_reported():
    with pytest.raises(standvirtual.SourceError):
        standvirtual.parse_search("<html>captcha</html>")


class FakeFetcher:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url):
        return self.pages.get(url)


def test_search_paginates_until_total():
    def results(ids, total):
        s = {"advertSearch": {"totalCount": total, "edges": [{"node": {"id": i}} for i in ids]}}
        return page({"props": {"pageProps": {"urqlState": {"x": {"data": json.dumps(s)}}}}})

    base = standvirtual.BASE + "/motos/honda/cb?page="
    f = FakeFetcher({base + "1": results(["1", "2"], 3), base + "2": results(["3"], 3)})
    assert [n["id"] for n in standvirtual.search(f, "/motos/honda/cb")] == ["1", "2", "3"]
