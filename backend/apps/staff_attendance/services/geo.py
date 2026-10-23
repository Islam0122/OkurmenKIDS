"""Расстояние до центра геозоны офиса."""
from __future__ import annotations

import math

EARTH_RADIUS_M = 6_371_008.8  # средний радиус Земли (IUGG)

# Допуск на погрешность вычислений с плавающей точкой: точка ровно на границе
# радиуса не должна отклоняться из-за 1e-9 метра. Сантиметр не меняет смысла
# проверки — точность GPS телефона в лучшем случае несколько метров.
DISTANCE_EPSILON_M = 0.01


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние по дуге большого круга между двумя точками, в метрах."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def within_radius(distance_m: float, radius_m: float) -> bool:
    return distance_m <= radius_m + DISTANCE_EPSILON_M
