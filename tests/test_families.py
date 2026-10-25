import pytest

from motas.families import classify, is_candidate


@pytest.mark.parametrize("slug,title,version,cc,expected", [
    # Real titles seen on Standvirtual.
    ("nx", "Honda NX  500", "500", 500, "NX500"),
    ("nx", "Honda NX  2025", "2025", 500, "NX500"),
    ("nx", "Honda NX  CB500X", "CB500X", None, "NX500"),
    ("nx", "Honda NX  500 (CAMPANHA EM VIGOR)", "500 (CAMPANHA EM VIGOR)", None, "NX500"),
    ("cb", "Honda CB  500 XA Carta A2", "500 XA Carta A2", 471, "CB500X"),
    ("cb", "Honda CB  CB500XA", "CB500XA", 471, "CB500X"),
    ("cb", "Honda CB  500X A2", "500X A2", 500, "CB500X"),
    ("cb", "Honda CB  500 X DE SERVIÇO", "500 X DE SERVIÇO", 500, "CB500X"),
    # Other bikes that share the model slug.
    ("nx", "Honda NX  4 FALCON", "4 FALCON", 397, None),
    ("nx", "Honda NX 650 Dominator", "650 Dominator", 644, None),
    ("cb", "Honda CB  500F", "500F", None, None),
    ("cb", "Honda CB  500 F -18 MESES DE GARANTIA", "500 F -18 MESES DE GARANTIA", 471, None),
    ("cb", "Honda CB  650 R - 18 MESES DE GARANTIA", "650 R", None, None),
    ("cbr", "Honda CBR  500 R E-CLUTCH 2026", "500 R E-CLUTCH 2026", None, None),
])
def test_classify_from_title(slug, title, version, cc, expected):
    assert classify(slug, title, version, cc) == expected


def test_vague_title_uses_description():
    assert classify("cb", "Honda CB", "", None, "Vendo CB500X de 2021, revisões na marca") == "CB500X"
    assert classify("cb", "Honda CB", "", None, "Vendo CB500F") is None
    # A description that mentions both models decides nothing.
    assert classify("cb", "Honda CB", "", None, "CB500X, não NX500") is None


def test_description_never_overrides_specific_title():
    assert classify("cb", "Honda CB 650 R", "", None, "Troco por CB500X") is None
    assert classify("cb", "Honda CB 500 F", "", None, "melhor que a CB500X") is None


def test_year_in_title_is_not_a_displacement():
    assert is_candidate("cb", "Honda CB 2021", "", None)


def test_candidates():
    assert is_candidate("cb", "Honda CB", "", None)
    assert not is_candidate("cb", "Honda CB 125", "125", 125)
    assert not is_candidate("nx", "Honda NX 4 FALCON", "4 FALCON", 397)
