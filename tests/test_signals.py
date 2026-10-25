from motas.signals import AMBER, GREEN, RED, listing_signals, text_signals


def labels(text):
    return {label for _, label in text_signals(text)}


def test_negated_falls_are_reassuring_not_warnings():
    assert labels("Mota impecável, nunca caiu.") == {"Seller states no falls"}
    assert labels("Não caiu, sem quedas.") == {"Seller states no falls"}
    assert "Mentions a fall" in labels("Teve uma pequena queda em parado.")
    assert "Mentions a fall" in labels("A mota caiu no parque.")


def test_crash_protection_is_not_a_fall():
    assert labels("Proteções de queda e barras de proteção") == set()


def test_common_phrases_do_not_trigger():
    assert labels("À partida é a mota ideal para quem precisa de mobilidade.") == set()
    assert labels("Sem riscos, sem mossas.") == set()


def test_red_flags():
    assert "Sold for parts" in labels("Vendo para peças")
    assert "Missing documents" in labels("Mota sem documentos")
    assert "Not running / mechanical fault" in labels("A mota não pega")
    assert "Legal encumbrance (lien)" in labels("Tem reserva de propriedade")


def test_listing_signals_order_and_dedup():
    listing = {
        "owners": 1, "service_book": False, "seller_type": "professional",
        "badges": ["WARRANTY"], "km": 60_000, "negotiable": True,
        "description": "Único dono. Garantia de 18 meses. Precisa de pneus.",
    }
    s = listing_signals(listing, age_years=2.0, days_listed=60, price_drop=300)
    levels = [lvl for lvl, _ in s]
    assert levels == sorted(levels, key=[RED, AMBER, GREEN].index)
    texts = [t for _, t in s]
    assert texts.count("Single owner") == 1
    assert "Warranty mentioned" not in texts      # covered by "Dealer warranty"
    assert "High use: 30,000 km/year" in texts
    assert "Needs work" in texts
    assert "Price already cut by €300" in texts
