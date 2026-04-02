from __future__ import annotations

import math


def calc_wind_zone(m_dot_kg_s: float, wind_m_s: float, coeff: float) -> float | None:
    """
    Универсальная формула для L и r0 из шаблона:
        L  = 25   * sqrt(M / W)
        r0 = 12.5 * sqrt(M / W)

    coeff = 25 или 12.5
    """
    if m_dot_kg_s <= 0 or wind_m_s <= 0:
        return None
    return coeff * math.sqrt(m_dot_kg_s / wind_m_s)
