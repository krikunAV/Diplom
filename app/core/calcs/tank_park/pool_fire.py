# app/core/calcs/tank_park/pool_fire.py
"""
Модуль 3 (diesel): тепловое излучение пожара пролива.

Нормативная основа:
  ГОСТ Р 12.3.047-2012, Приложение Б — тепловое излучение пламени
  Формула Томаса — высота пламени пожара пролива (B.12/B.13)
  ГОСТ Р 12.3.047-2012, Табл.Б.1 — SEP для разных топлив

Физическая модель:
  Пролив моделируется как вертикальный цилиндр (пламя):
    D_pool = √(4·F_пр / π)          — диаметр пролива / основания пламени
    L_F    = 42·D·(ṁ"/(ρ·√(g·D)))^0.61   — высота пламени (Томас)
    H      = L_F / 2                — высота центра тяжести пламени

  Угловой коэффициент — ГОСТ Б.5–Б.15 (цилиндр),
  тот же алгоритм _fq_gost что и в jet_fire.py.

  q(r) = E_f · F_q(r) · τ(r)       [кВт/м²]

Входные данные из ctx.inputs:
  spill.area_m2               — площадь пролива, м²
  fuel.Ef_pool_kw_m2          — SEP пламени пролива, кВт/м²
  fuel.burn_rate_kg_m2_s      — удельная скорость выгорания, кг/(м²·с)

Записывает в ctx.results:
  pool_fire  — dict с params, table, zones (как jet_fire / fireball)
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

from app.core.context import CalculationContext
from app.core.calcs.fire.jet_fire import _fq_gost   # переиспользуем формулы ГОСТ Б.5–Б.15


# Физические константы
_RHO_AIR = 1.2      # кг/м³
_G       = 9.81     # м/с²
_ATM_ABS = 7e-4     # коэффициент поглощения атмосферы (ГОСТ Б.4)


def _thomas_flame_height(D: float, burn_rate: float) -> float:
    """
    Высота пламени пожара пролива по формуле Томаса (ГОСТ Б.12):

        L_F / D = 42 · (ṁ" / (ρ_air · √(g·D)))^0.61

    Параметры:
      D         — диаметр пролива, м
      burn_rate — удельная скорость выгорания, кг/(м²·с)
    """
    denom = _RHO_AIR * math.sqrt(_G * D)
    if denom <= 0:
        return D
    ratio = (burn_rate / denom) ** 0.61
    return 42.0 * D * ratio


def calc_pool_fire(
    *,
    area_m2: float,
    burn_rate_kg_m2_s: float,
    Ef_kw_m2: float,
) -> Dict[str, Any]:
    """
    Расчёт теплового излучения пожара пролива.

    Геометрия:
      D_pool    = √(4·F / π)
      L_F       = Thomas formula
      H_center  = L_F / 2

    Угловой коэффициент Fq — ГОСТ Б.5–Б.15 (_fq_gost, переиспользование).
    Коэффициент пропускания τ — ГОСТ Б.4 (экспоненциальная модель).

    Зоны поражения: пороги 1.4 / 4.2 / 7.0 / 10.5 кВт/м².
    """
    if area_m2 <= 0:
        return {"skip_reason": "area_m2 ≤ 0, пожар пролива не рассчитывается."}

    D = math.sqrt(4.0 * area_m2 / math.pi)
    LF = _thomas_flame_height(D, burn_rate_kg_m2_s)
    H_c = LF / 2.0

    def _tau(r: float) -> float:
        """Коэффициент пропускания атмосферы (ГОСТ Б.4)."""
        X_3d = math.sqrt(r * r + H_c * H_c)
        dist = max(0.0, X_3d - D / 2.0)
        return math.exp(-_ATM_ABS * dist)

    # Сетка расстояний
    r_grid: List[float] = (
        [0, 1, 2, 3, 5]
        + list(range(10, 101, 5))
        + [125, 150, 200]
    )

    rows = []
    for r in r_grid:
        rf = float(r)
        t = _tau(rf)
        # Переиспользуем ГОСТ Б.5–Б.15:
        # для пожара пролива L = высота пламени, d = диаметр пролива
        fq = _fq_gost(L=LF, d=D, X=rf)
        q = Ef_kw_m2 * fq * t
        rows.append({
            "r_m":     rf,
            "tau":     round(t, 6),
            "Fq":      round(fq, 6),
            "q_kw_m2": round(q, 4),
        })

    # Поиск радиусов зон по пороговым значениям
    thresholds = [1.4, 4.2, 7.0, 10.5]
    zones = []
    for thr in thresholds:
        r_thr = None
        for i in range(len(rows) - 1):
            r0, q0 = rows[i]["r_m"], rows[i]["q_kw_m2"]
            r1, q1 = rows[i + 1]["r_m"], rows[i + 1]["q_kw_m2"]
            if abs(q0 - thr) < 1e-9:
                r_thr = r0
                break
            if (q0 - thr) * (q1 - thr) < 0:
                frac = (thr - q0) / (q1 - q0)
                r_thr = r0 + frac * (r1 - r0)
                break
        zones.append({
            "q_thr_kw_m2": thr,
            "r_m": None if r_thr is None else round(r_thr, 1),
        })

    return {
        "params": {
            "area_m2":            round(area_m2, 2),
            "D_pool_m":           round(D, 2),
            "LF_m":               round(LF, 2),
            "H_center_m":         round(H_c, 2),
            "burn_rate_kg_m2_s":  float(burn_rate_kg_m2_s),
            "Ef_kw_m2":           float(Ef_kw_m2),
        },
        "table": rows,
        "zones": zones,
    }


def run_pool_fire(ctx: CalculationContext) -> None:
    """
    Контекстный wrapper для calc_pool_fire.

    Читает из ctx.inputs:
      spill.area_m2
      fuel.Ef_pool_kw_m2
      fuel.burn_rate_kg_m2_s

    Пишет в ctx.results:
      pool_fire  — полный результат расчёта
    """
    spill = ctx.inputs["spill"]
    fuel = ctx.inputs["fuel"]

    area_m2 = float(spill["area_m2"])
    Ef = float(fuel.get("Ef_pool_kw_m2", 25.0))
    burn_rate = float(fuel.get("burn_rate_kg_m2_s", 0.04))

    result = calc_pool_fire(
        area_m2=area_m2,
        burn_rate_kg_m2_s=burn_rate,
        Ef_kw_m2=Ef,
    )
    ctx.results["pool_fire"] = result

    if "skip_reason" not in result:
        ctx.log(
            f"[pool_fire] D={result['params']['D_pool_m']} м, "
            f"L_F={result['params']['LF_m']} м, "
            f"Ef={Ef} кВт/м²"
        )
    else:
        ctx.log(f"[pool_fire] пропуск: {result['skip_reason']}")
