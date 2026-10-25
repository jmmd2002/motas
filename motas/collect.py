"""Collect a family's listings from Standvirtual into the database.

Usage: python -m motas.collect [family]
"""

import sys
from collections.abc import Callable

from . import db, standvirtual
from .families import FAMILIES, Family, classify, is_candidate


def collect(family: Family, conn, fetcher: standvirtual.Fetcher | None = None,
            progress: Callable[[str], None] = lambda msg: None) -> int:
    """Refresh the family's listings. Returns the number of active listings."""
    fetcher = fetcher or standvirtual.Fetcher()

    candidates: dict[str, dict] = {}
    for path in family.searches:
        progress(f"Searching {path}")
        for node in standvirtual.search(fetcher, path):
            s = standvirtual.node_summary(node)
            if is_candidate(s["model"], s["title"], s["version"], s["cc"]):
                prev = candidates.get(s["id"], {})
                s["badges"] = sorted(set(prev.get("badges", [])) | set(s["badges"]))
                candidates[s["id"]] = s

    seen_at = db.now()
    seen: set[str] = set()
    for i, c in enumerate(candidates.values(), 1):
        progress(f"Reading listing {i}/{len(candidates)}")
        page = fetcher.get(c["url"])
        listing = standvirtual.parse_ad(page) if page else None
        if listing is None:
            continue
        generation = classify(listing["model"], listing["title"], listing["version"],
                              listing["cc"], listing["description"])
        if generation is None:
            continue
        listing.update(family=family.key, generation=generation, badges=c["badges"])
        db.upsert(conn, listing, seen_at)
        seen.add(listing["id"])

    if not seen:
        # Never wipe the stored market because one run came back empty.
        conn.rollback()
        raise standvirtual.SourceError("no listings found; source may have changed")
    db.finish_run(conn, family.key, seen, seen_at)
    return len(seen)


def main() -> None:
    key = sys.argv[1] if len(sys.argv) > 1 else "nx500"
    family = FAMILIES[key]
    with db.connect() as conn:
        n = collect(family, conn, progress=print)
    print(f"{n} active {family.label} listings")


if __name__ == "__main__":
    main()
