from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.context import CalculationContext


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


def run_wind_zones(ctx: "CalculationContext") -> None:
    """
    Модуль расчёта ветровых зон.

    Читает: ctx.intermediate["m_dot_kg_s"]
    Пишет:  ctx.results["wind_zones"]
    """
    m_dot = float(ctx.intermediate.get("m_dot_kg_s", 0.0) or 0.0)
    ctx.results["wind_zones"] = {
        "L_wind1_m":  calc_wind_zone(m_dot, 1.0, 25.0),
        "L_wind3_m":  calc_wind_zone(m_dot, 3.0, 25.0),
        "r0_wind1_m": calc_wind_zone(m_dot, 1.0, 12.5),
        "r0_wind3_m": calc_wind_zone(m_dot, 3.0, 12.5),
    }
    ctx.log(f"[wind] ветровые зоны: m_dot={m_dot:.4f} kg/s")
