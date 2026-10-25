"""Where the buyer is, and how far each bike is."""

from math import asin, cos, radians, sin, sqrt

# District capitals (and the two autonomous-region capitals).
PLACES = {
    "Aveiro": (40.6405, -8.6538),
    "Beja": (38.0151, -7.8632),
    "Braga": (41.5454, -8.4265),
    "Bragança": (41.8061, -6.7567),
    "Castelo Branco": (39.8222, -7.4909),
    "Coimbra": (40.2033, -8.4103),
    "Évora": (38.5714, -7.9135),
    "Faro": (37.0194, -7.9304),
    "Funchal": (32.6669, -16.9241),
    "Guarda": (40.5373, -7.2658),
    "Leiria": (39.7436, -8.8071),
    "Lisboa": (38.7223, -9.1393),
    "Ponta Delgada": (37.7412, -25.6756),
    "Portalegre": (39.2967, -7.4285),
    "Porto": (41.1579, -8.6291),
    "Santarém": (39.2362, -8.6859),
    "Setúbal": (38.5244, -8.8882),
    "Viana do Castelo": (41.6932, -8.8329),
    "Vila Real": (41.3006, -7.7441),
    "Viseu": (40.6566, -7.9125),
}


def distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance (straight line, not road distance)."""
    lat1, lon1, lat2, lon2 = map(radians, (*a, *b))
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * 6371 * asin(sqrt(h))
