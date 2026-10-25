from datetime import date

import numpy as np

from motas import analysis, db
from motas.families import NX500

TODAY = date(2026, 10, 25)


def listing(i, price, km, year, month=6, gen="NX500", **kw):
    base = {
        "id": str(i), "family": "nx500", "generation": gen, "url": f"https://x/{i}",
        "title": f"Honda {gen}", "version": "", "price": price, "negotiable": False,
        "km": km, "reg_year": year, "reg_month": month, "power_cv": 47, "cc": 471,
        "owners": None, "service_book": None, "second_key": None, "origin": "national",
        "condition": "used", "is_parts": False, "seller_type": "professional",
        "seller_name": "Dealer", "region": "Lisboa", "city": "Lisboa",
        "lat": 38.72, "lon": -9.14, "features": [], "badges": [], "description": "",
        "photo_url": None, "photo_count": 0, "listed_at": "2026-10-01T00:00:00+00:00",
    }
    base.update(kw)
    return base


def market(extra=()):
    rng = np.random.default_rng(0)
    rows = []
    for i in range(14):
        year = int(rng.integers(2019, 2026))
        km = int(rng.integers(500, 40_000))
        price = round(7000 * 0.96 ** (km / 10_000) * 0.94 ** (2026 - year) * rng.normal(1, 0.02))
        rows.append(listing(i, price, km, year, gen="NX500" if year >= 2024 else "CB500X"))
    return rows + list(extra)


def test_new_bikes_are_a_reference_not_valued():
    m = analysis.analyze(market([listing(99, 6900, 1, 2026, condition="new")]), {}, NX500, TODAY)
    assert "99" not in set(m.table["id"])
    assert list(m.new["id"]) == ["99"]


def test_duplicates_flagged_and_only_cheapest_fitted():
    dup = [listing(50, 6550, 822, 2025, 9, gen="CB500X"), listing(51, 6750, 822, 2025, 9)]
    m = analysis.analyze(market(dup), {}, NX500, TODAY)
    t = m.table.set_index("id")
    assert t.loc["51", "duplicate_of_cheaper"] and not t.loc["50", "duplicate_of_cheaper"]
    assert any("listed again at €6,750" in s for _, s in t.loc["50", "signals"])
    fitted_ids = set(m.table.loc[m.table["in_model"], "id"])
    assert "50" in fitted_ids and "51" not in fitted_ids


def test_previous_gen_registered_after_launch_is_relabelled():
    m = analysis.analyze(market([listing(60, 6250, 3000, 2025, gen="CB500X")]), {}, NX500, TODAY)
    row = m.table.set_index("id").loc["60"]
    assert row["generation"] == "NX500"
    assert any("Confirm the model" in s for _, s in row["signals"])


def test_red_flag_listing_is_not_fitted_and_sorted_last():
    bad = listing(70, 2500, 10_000, 2022, description="Vendo para peças")
    m = analysis.analyze(market([bad]), {}, NX500, TODAY)
    assert m.table.iloc[-1]["id"] == "70"
    assert m.table.iloc[-1]["verdict"] == "Check first"
    assert not m.table.iloc[-1]["in_model"]


def test_price_drop_and_distance():
    m = analysis.analyze(market(), {"0": [("t0", 99_999)]}, NX500, TODAY, home=(41.1579, -8.6291))
    row = m.table.set_index("id").loc["0"]
    assert row["price_drop"] == 99_999 - row["price"]
    assert 270 < row["distance_km"] < 290      # Porto to Lisboa, straight line


def test_db_tracks_price_changes_and_removals(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    a, b = listing(1, 6000, 1000, 2025), listing(2, 5000, 20_000, 2021)
    db.upsert(conn, a, "2026-10-01")
    db.upsert(conn, b, "2026-10-01")
    db.finish_run(conn, "nx500", {"1", "2"}, "2026-10-01")

    db.upsert(conn, {**a, "price": 5800}, "2026-10-02")
    db.finish_run(conn, "nx500", {"1"}, "2026-10-02")

    active = db.active_listings(conn, "nx500")
    assert [l["id"] for l in active] == ["1"]
    assert active[0]["price"] == 5800 and active[0]["first_seen"] == "2026-10-01"
    assert db.price_history(conn, ["1"])["1"] == [("2026-10-01", 6000), ("2026-10-02", 5800)]
    assert db.last_run(conn, "nx500") == "2026-10-02"
