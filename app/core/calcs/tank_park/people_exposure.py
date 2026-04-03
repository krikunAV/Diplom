# app/core/calcs/tank_park/people_exposure.py
"""
Модуль: оценка числа людей, попавших в зоны теплового поражения.

Нормативная основа:
  Ростехнадзор №412, п.8 — оценка числа поражённых
  РД 03-409-01, Прил.6   — формулы зон поражения людей
  МЧС Методика 2009, п.3 — персонал в зонах поражения

Физическая модель:
  Каждая «зона поражения» задаётся радиусом r_m (расстояние, при котором
  интенсивность теплового излучения падает до порогового значения q).

  Площадь зоны: A = π · r²  [м²]
  Число людей:  N = A [га] · ρ [чел/га]   где ρ — плотность персонала

  Предполагается открытое пространство, равномерное распределение персонала.

Входные данные из ctx.inputs:
  exposure.people_density_per_ha — плотность персонала, чел/га (default 0)

Читает из ctx.results (всё опционально):
  jet_fire.zones     — зоны факела  (lpg)
  pool_fire.zones    — зоны пожара пролива  (diesel)
  fireball.zones     — зоны огненного шара  (diesel + lpg)

Записывает в ctx.results:
  people_exposure — структура с зонами и числом людей per zone
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

from app.core.context import CalculationContext


def _zones_with_people(
    zones: Optional[List[Dict[str, Any]]],
    density_per_ha: float,
) -> List[Dict[str, Any]]:
    """
    Для каждой зоны вычисляет площадь и оценочное число людей.

    Зоны — список {"q_thr_kw_m2": ..., "r_m": ...}.
    Возвращает расширенный список с полями:
      area_m2   — площадь зоны, м²
      area_ha   — то же в га
      n_people  — расчётное число людей (None если density == 0)
    """
    out = []
    for z in (zones or []):
        r_m = z.get("r_m")
        q = z.get("q_thr_kw_m2")

        if r_m is not None and float(r_m) > 0:
            r = float(r_m)
            area_m2 = math.pi * r * r
            area_ha = area_m2 / 10_000.0
            n_people = round(area_ha * density_per_ha, 1) if density_per_ha > 0 else None
        else:
            area_m2 = None
            area_ha = None
            n_people = None

        out.append({
            "q_thr_kw_m2": q,
            "r_m":          r_m,
            "area_m2":      round(area_m2, 1) if area_m2 is not None else None,
            "area_ha":      round(area_ha, 3) if area_ha is not None else None,
            "n_people":     n_people,
        })
    return out


def run_people_exposure(ctx: CalculationContext) -> None:
    """
    Оценка числа людей в зонах теплового поражения.

    Запускается ПОСЛЕДНИМ в pipeline — после расчёта всех тепловых зон.
    Если плотность персонала = 0, записывает только площади зон.
    """
    exposure = ctx.inputs.get("exposure", {}) or {}
    density = float(exposure.get("people_density_per_ha", 0.0))

    jf_zones = (ctx.results.get("jet_fire") or {}).get("zones")
    pf_zones = (ctx.results.get("pool_fire") or {}).get("zones")
    fb_zones = (ctx.results.get("fireball") or {}).get("zones")

    result: Dict[str, Any] = {
        "density_per_ha": density,
        "jet_fire":  _zones_with_people(jf_zones, density),
        "pool_fire": _zones_with_people(pf_zones, density),
        "fireball":  _zones_with_people(fb_zones, density),
    }

    ctx.results["people_exposure"] = result

    n_zones = sum(
        len(v) for v in (result["jet_fire"], result["pool_fire"], result["fireball"])
        if v
    )
    ctx.log(
        f"[people_exposure] плотность={density} чел/га, "
        f"зон для анализа={n_zones}"
    )
