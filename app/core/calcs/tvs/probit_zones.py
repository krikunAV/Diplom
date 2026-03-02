# app/core/calcs/tvs/probit_zones.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional

from app.core.context import CalculationContext


# -------------------- helpers --------------------

def _first_crossing_radius(
    r_grid: List[float],
    y: List[float],
    threshold: float,
) -> Optional[float]:
    """
    Находит радиус, где y(r) впервые становится <= threshold (монотонно убывающая кривая).
    Возвращает радиус с линейной интерполяцией.
    Если везде выше threshold -> None (не достигли).
    Если уже в первой точке <= threshold -> r_grid[0].
    """
    if not r_grid or not y or len(r_grid) != len(y):
        raise ValueError("r_grid and y must be non-empty lists of same length")

    if y[0] <= threshold:
        return float(r_grid[0])

    for i in range(1, len(r_grid)):
        if y[i] <= threshold:
            r1, r2 = float(r_grid[i - 1]), float(r_grid[i])
            y1, y2 = float(y[i - 1]), float(y[i])
            if y2 == y1:
                return float(r2)
            # линейная интерполяция по y
            t = (threshold - y1) / (y2 - y1)
            return r1 + t * (r2 - r1)

    return None


def _zones_from_ranges(
    r_grid: List[float],
    y: List[float],
    ranges: List[Tuple[str, float, float]],
) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
    """
    Формирует зоны по диапазонам значений y:
      label, y_high, y_low  (например 100kPa..70kPa)
    Возвращает радиальные границы (r_in, r_out) где y ∈ (y_low..y_high].
    Предполагается монотонное убывание y(r).

    Пример:
      ranges=[("A", inf, 100kPa), ("B", 100kPa, 70kPa), ...]
    """
    out: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
    for label, y_high, y_low in ranges:
        # r_in: где y падает ниже y_high (граница "сверху")
        # r_out: где y падает ниже y_low (граница "снизу")
        r_in = None if y_high == float("inf") else _first_crossing_radius(r_grid, y, y_high)
        r_out = _first_crossing_radius(r_grid, y, y_low)
        out[label] = (r_in, r_out)
    return out


def _kpa_to_pa(kpa: float) -> float:
    return float(kpa) * 1000.0


# -------------------- API --------------------

@dataclass
class ZonesResult:
    zones_glass: Dict[str, Optional[float]]
    zones_buildings: Dict[str, Tuple[Optional[float], Optional[float]]]
    zones_people: Dict[str, Optional[float]]
    params: Dict[str, float]


def run_probit_zones(ctx: CalculationContext) -> ZonesResult:
    """
    Block 3: Радиусы зон (без мат.ущерба и жертв).

    ВАЖНО:
    - Для прототипа считаем зоны ДЕТЕРМИНИРОВАННО по ΔP(r) из Block 2:
      * остекление: 1-2, 2-5, 5-10 кПа (по факту берём пороги 2, 5, 10 кПа)
      * здания (A–E): по диапазонам ΔP (пороговые значения можно скорректировать под твой шаблон)

    - Probit для людей можно добавить позже (с I+ и формулами Pr). Сейчас оставляем "каркас" и
      возможность задавать пороги по ΔP для степеней поражения.

    Требует:
      ctx.results["r_grid_m"], ctx.results["dP_Pa"]

    Пишет:
      ctx.results["zones_glass"], ctx.results["zones_buildings"], ctx.results["zones_people"]
    """
    r_grid = ctx.results.get("r_grid_m")
    dP = ctx.results.get("dP_Pa")

    if r_grid is None or dP is None:
        raise ValueError("run_probit_zones requires ctx.results['r_grid_m'] and ctx.results['dP_Pa'] (run Block 2 first)")

    r_grid = [float(x) for x in r_grid]
    dP = [float(x) for x in dP]

    # -------------------- Glass zones (thresholds) --------------------
    # В шаблонах обычно используют границы по ΔP:
    # 1–2 кПа, 2–5 кПа, 5–10 кПа.
    # Для радиуса удобно брать ВЕРХНЮЮ границу зоны как "порог разрушения":
    # r(10кПа), r(5кПа), r(2кПа)
    glass_thresholds_kpa = {
        "glass_5_10_kPa": 10.0,
        "glass_2_5_kPa": 5.0,
        "glass_1_2_kPa": 2.0,
    }
    zones_glass: Dict[str, Optional[float]] = {
        name: _first_crossing_radius(r_grid, dP, _kpa_to_pa(thr))
        for name, thr in glass_thresholds_kpa.items()
    }

    # -------------------- Building damage zones (A–E by ΔP) --------------------
    # Здесь НУЖНО будет подогнать пороги под твой шаблон 7.1.
    # Я ставлю типовые демонстрационные пороги в кПа (часто встречаются в учебных/шаблонных расчётах):
    #   A: >100 кПа (практически полное разрушение)
    #   B: 70–100 кПа
    #   C: 30–70 кПа
    #   D: 12–30 кПа
    #   E: 5–12 кПа
    #
    # Важно: мы возвращаем радиальные границы (r_in, r_out) для каждой категории.
    building_ranges_kpa = [
        ("A", float("inf"), 100.0),
        ("B", 100.0, 70.0),
        ("C", 70.0, 30.0),
        ("D", 30.0, 12.0),
        ("E", 12.0, 5.0),
    ]
    building_ranges_pa = [
        (label, _kpa_to_pa(high) if high != float("inf") else float("inf"), _kpa_to_pa(low))
        for (label, high, low) in building_ranges_kpa
    ]
    zones_buildings = _zones_from_ranges(r_grid, dP, building_ranges_pa)

    # -------------------- People zones (placeholder) --------------------
    # Для прототипа (без probit) — можно взять пороги по ΔP, например:
    # лёгкие травмы / средние / тяжёлые. Это НЕ заменяет пробит, но позволяет дать радиусы зон.
    # Позже заменим на Pr(I+,ΔP) + вероятность.
    people_thresholds_kpa = {
        # подгони под свой шаблон, если там иные пороги
        "people_severe_kPa": 70.0,
        "people_moderate_kPa": 30.0,
        "people_light_kPa": 12.0,
    }
    zones_people: Dict[str, Optional[float]] = {
        name: _first_crossing_radius(r_grid, dP, _kpa_to_pa(thr))
        for name, thr in people_thresholds_kpa.items()
    }

    # -------------------- Save to context --------------------
    ctx.results["zones_glass"] = zones_glass
    ctx.results["zones_buildings"] = zones_buildings
    ctx.results["zones_people"] = zones_people

    ctx.log("[zones] computed zones for glass/buildings/people (ΔP-based)")

    return ZonesResult(
        zones_glass=zones_glass,
        zones_buildings=zones_buildings,
        zones_people=zones_people,
        params={
            "glass_thr_kPa_10": 10.0,
            "glass_thr_kPa_5": 5.0,
            "glass_thr_kPa_2": 2.0,
            "bld_A_low_kPa": 100.0,
            "bld_B_low_kPa": 70.0,
            "bld_C_low_kPa": 30.0,
            "bld_D_low_kPa": 12.0,
            "bld_E_low_kPa": 5.0,
        },
    )