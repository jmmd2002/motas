"""Model families: groups of listings that are priced against each other.

The NX500 (2024-) is the renamed, updated successor of the CB500X (2013-2023):
same 471 cc A2-compliant twin and chassis. Pooling both gives the price model
enough data; the model itself decides whether the generation matters.
"""

import re
from dataclasses import dataclass

from .text import strip_accents


@dataclass(frozen=True)
class Family:
    key: str
    label: str
    # Standvirtual search paths whose results may contain family members.
    searches: tuple[str, ...]
    # Year the newest generation was introduced (used for the mislabel check).
    current_gen_year: int
    current_gen: str
    previous_gen: str


NX500 = Family(
    key="nx500",
    label="Honda NX500 / CB500X",
    searches=(
        "/motos/honda/nx",
        "/motos/honda/cb",
        "/motos/honda/q-cb500x",
        "/motos/honda/q-nx500",
    ),
    current_gen_year=2024,
    current_gen="NX500",
    previous_gen="CB500X",
)

FAMILIES = {NX500.key: NX500}

# Any displacement-like number other than 500 in the title means another bike
# (e.g. "NX 650 Dominator", "CB 650 R"). Three digits only, so a year in the
# title ("Honda CB 2021") is not mistaken for one.
_OTHER_DISPLACEMENT = re.compile(r"(?<!\d)(?!500)\d{3}(?!\d)")


def _squash(s: str) -> str:
    return re.sub(r"[\s\-_/]+", "", strip_accents(s).upper())


def _vague(slug: str, name: str, cc: int | None) -> bool:
    """A CB/NX title that names no specific bike, so the description decides."""
    return (slug in ("nx", "cb")
            and not _OTHER_DISPLACEMENT.search(name)
            and not re.search(r"500\s*[FRS]\b", name.upper())
            and (cc is None or 450 <= cc <= 520))


def is_candidate(model_slug: str | None, title: str, version: str, cc: int | None) -> bool:
    """Whether a search result is worth opening (search results lack descriptions)."""
    return (classify(model_slug, title, version, cc) is not None
            or _vague((model_slug or "").lower(), f"{title} {version}", cc))


def classify(model_slug: str | None, title: str, version: str,
             cc: int | None, description: str = "") -> str | None:
    """Return 'NX500', 'CB500X' or None for a Honda listing.

    Title/version are trusted first; the description is only consulted when
    the title is too vague to decide (e.g. just "Honda CB").
    """
    name = f"{title} {version}"
    sq = _squash(name)
    slug = (model_slug or "").lower()

    if "NX500" in sq or (slug == "nx" and "500" in sq):
        return "NX500"
    if "CB500X" in sq or (slug == "cb" and "500X" in sq):
        return "CB500X"
    if slug == "nx" and cc is not None and 450 <= cc <= 520:
        return "NX500"

    if _vague(slug, name, cc) and description:
        dq = _squash(description)
        has_nx, has_cb = "NX500" in dq, "CB500X" in dq
        if has_nx and not has_cb:
            return "NX500"
        if has_cb and not has_nx:
            return "CB500X"
    return None
