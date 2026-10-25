"""SQLite storage: current listing state plus price history."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "motas.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS listings (
    id TEXT PRIMARY KEY,
    family TEXT NOT NULL,
    generation TEXT NOT NULL,
    url TEXT NOT NULL,
    title TEXT, version TEXT,
    price INTEGER, negotiable INTEGER,
    km INTEGER, reg_year INTEGER, reg_month INTEGER,
    power_cv INTEGER, cc INTEGER,
    owners INTEGER, service_book INTEGER, second_key INTEGER,
    origin TEXT, condition TEXT, is_parts INTEGER,
    seller_type TEXT, seller_name TEXT,
    region TEXT, city TEXT, lat REAL, lon REAL,
    features TEXT, badges TEXT, description TEXT,
    photo_url TEXT, photo_count INTEGER,
    listed_at TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS price_history (
    listing_id TEXT NOT NULL REFERENCES listings(id),
    seen_at TEXT NOT NULL,
    price INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS price_history_listing ON price_history(listing_id);
CREATE TABLE IF NOT EXISTS runs (
    family TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    listings INTEGER NOT NULL
);
"""

_COLUMNS = (
    "family", "generation", "url", "title", "version", "price", "negotiable", "km",
    "reg_year", "reg_month", "power_cv", "cc", "owners", "service_book", "second_key",
    "origin", "condition", "is_parts", "seller_type", "seller_name", "region", "city",
    "lat", "lon", "features", "badges", "description", "photo_url", "photo_count",
    "listed_at",
)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | str = DEFAULT_PATH) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    # Streamlit reruns the script on different threads; access is sequential.
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def upsert(conn: sqlite3.Connection, listing: dict, seen_at: str) -> None:
    """Insert or refresh a listing; record a price point when the price changes."""
    row = {c: listing.get(c) for c in _COLUMNS}
    row["features"] = json.dumps(listing.get("features") or [], ensure_ascii=False)
    row["badges"] = json.dumps(listing.get("badges") or [])
    prev = conn.execute("SELECT price FROM listings WHERE id = ?", (listing["id"],)).fetchone()

    if prev is None:
        cols = ", ".join(("id", *_COLUMNS, "first_seen", "last_seen", "active"))
        marks = ", ".join("?" * (len(_COLUMNS) + 4))
        conn.execute(f"INSERT INTO listings ({cols}) VALUES ({marks})",
                     (listing["id"], *row.values(), seen_at, seen_at, 1))
    else:
        sets = ", ".join(f"{c} = ?" for c in _COLUMNS)
        conn.execute(f"UPDATE listings SET {sets}, last_seen = ?, active = 1 WHERE id = ?",
                     (*row.values(), seen_at, listing["id"]))

    if listing.get("price") is not None and (prev is None or prev["price"] != listing["price"]):
        conn.execute("INSERT INTO price_history VALUES (?, ?, ?)",
                     (listing["id"], seen_at, listing["price"]))


def finish_run(conn: sqlite3.Connection, family: str, seen_ids: set[str], finished_at: str) -> None:
    """Mark listings of a family not seen in this run as inactive (sold or removed)."""
    marks = ", ".join("?" * len(seen_ids))
    conn.execute(f"UPDATE listings SET active = 0 WHERE family = ? AND id NOT IN ({marks})",
                 (family, *seen_ids))
    conn.execute("INSERT INTO runs VALUES (?, ?, ?)", (family, finished_at, len(seen_ids)))
    conn.commit()


def last_run(conn: sqlite3.Connection, family: str) -> str | None:
    r = conn.execute("SELECT MAX(finished_at) FROM runs WHERE family = ?", (family,)).fetchone()
    return r[0]


def active_listings(conn: sqlite3.Connection, family: str) -> list[dict]:
    rows = conn.execute("SELECT * FROM listings WHERE family = ? AND active = 1", (family,))
    out = []
    for r in rows:
        d = dict(r)
        d["features"] = json.loads(d["features"] or "[]")
        d["badges"] = json.loads(d["badges"] or "[]")
        out.append(d)
    return out


def price_history(conn: sqlite3.Connection, listing_ids: list[str]) -> dict[str, list[tuple[str, int]]]:
    out: dict[str, list[tuple[str, int]]] = {i: [] for i in listing_ids}
    if not listing_ids:
        return out
    marks = ", ".join("?" * len(listing_ids))
    for r in conn.execute(f"SELECT listing_id, seen_at, price FROM price_history "
                          f"WHERE listing_id IN ({marks}) ORDER BY seen_at", listing_ids):
        out[r["listing_id"]].append((r["seen_at"], r["price"]))
    return out
