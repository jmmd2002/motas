"""Facts about a listing that should change a buyer's decision, besides price.

Each signal is (level, text) with level one of:
  'red'   - deal-breaker until clarified; the listing is left out of the price model
  'amber' - worth asking the seller about
  'green' - genuinely reassuring
"""

import re

from .text import fold

RED, AMBER, GREEN = "red", "amber", "green"

# Patterns run on fold()-ed text (lowercase, no accents).
_RED_TEXT = [
    (r"para pecas|so pecas", "Sold for parts"),
    (r"sem documentos|sem papeis|sem livrete|documentos? em falta", "Missing documents"),
    (r"acidentad|sinistrad|salvado|perda total", "Accident / salvage history"),
    (r"nao (pega|arranca|trabalha)|motor (partido|avariado|gripado)|avariad", "Not running / mechanical fault"),
    (r"penhora|reserva de propriedade|com divida", "Legal encumbrance (lien)"),
    (r"por legalizar|matricula estrangeira", "Not registered in Portugal"),
]
_AMBER_TEXT = [
    (r"(?<!nunca )(?<!nao )(teve|sofreu|deu) (uma )?(pequena |ligeira )?queda|(?<!nunca )(?<!nao )caiu|tombo",
     "Mentions a fall"),
    (r"amolgad|riscad|(?<!sem )riscos|(?<!sem )mossas", "Mentions damage or scratches"),
    (r"(precisa|necessita) de (reparacao|arranjo|pneus|bateria|revisao|manutencao|pintura|"
     r"kit|embraiagem|travoes|pastilhas)", "Needs work"),
]
_GREEN_TEXT = [
    (r"nunca caiu|sem quedas|nunca teve (quedas|acidentes)|sem acidentes", "Seller states no falls"),
    (r"revis(oes|ao) (na|feitas na|sempre na) (marca|honda|concessionario)|revisoes na honda",
     "Serviced at the dealer"),
    (r"unico dono|1 dono|um so dono|primeiro dono", "Single owner"),
    (r"garantia", "Warranty mentioned"),
]

HIGH_KM_PER_YEAR = 12_000
LONG_LISTED_DAYS = 45


def text_signals(description: str) -> list[tuple[str, str]]:
    t = fold(description)
    out = []
    for level, rules in ((RED, _RED_TEXT), (AMBER, _AMBER_TEXT), (GREEN, _GREEN_TEXT)):
        for pattern, label in rules:
            if re.search(pattern, t):
                out.append((level, label))
    return out


def listing_signals(l: dict, age_years: float | None, days_listed: int | None,
                    price_drop: int | None) -> list[tuple[str, str]]:
    """All signals for a listing, deal-breakers first."""
    s: list[tuple[str, str]] = []
    if l.get("is_parts"):
        s.append((RED, "Listed as parts"))

    if l.get("origin") == "imported":
        s.append((AMBER, "Imported"))
    owners = l.get("owners")
    if owners is not None and owners >= 3:
        s.append((AMBER, f"{owners} previous owners"))
    if l.get("service_book") is False:
        s.append((AMBER, "Service book not complete"))
    if l.get("second_key") is False:
        s.append((AMBER, "No spare key"))
    km = l.get("km")
    if km is not None and age_years and age_years >= 0.5 and km / age_years > HIGH_KM_PER_YEAR:
        s.append((AMBER, f"High use: {km / age_years:,.0f} km/year"))

    if l.get("seller_type") == "professional" and "WARRANTY" in (l.get("badges") or []):
        s.append((GREEN, "Dealer warranty"))
    if owners == 1:
        s.append((GREEN, "Single owner"))
    if l.get("service_book") is True:
        s.append((GREEN, "Complete service book"))

    s.extend(text_signals(l.get("description") or ""))

    # Negotiation leverage.
    if price_drop:
        s.append((GREEN, f"Price already cut by €{price_drop:,}"))
    if days_listed is not None and days_listed >= LONG_LISTED_DAYS:
        s.append((GREEN, f"Listed for {days_listed} days: room to negotiate"))
    if l.get("negotiable"):
        s.append((GREEN, "Price marked negotiable"))

    # A text signal can repeat a structured one; keep the first.
    seen, unique = set(), []
    if (GREEN, "Dealer warranty") in s:
        seen.add("Warranty mentioned")
    for sig in s:
        if sig[1] not in seen:
            seen.add(sig[1])
            unique.append(sig)
    order = {RED: 0, AMBER: 1, GREEN: 2}
    return sorted(unique, key=lambda x: order[x[0]])
