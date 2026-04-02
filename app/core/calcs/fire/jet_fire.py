from __future__ import annotations

import math
from typing import Dict, Any


def calc_jetfire_by_M(*, M_kg_s: float, K: float = 12.5, Ef_kw_m2: float = 80.0) -> Dict[str, Any]:
    """
    Упрощённый расчёт факельного горения:
      Lf = K * M^0.4
      Df = 0.15 * Lf

    Затем считаем:
    - коэффициент пропускания атмосферы tau(r),
    - угловой коэффициент Fq(r),
    - интенсивность теплового излучения q(r).

    По q строим зоны для порогов:
      1.4 / 4.2 / 7.0 / 10.5 кВт/м2
    """
    LF = K * (M_kg_s ** 0.4) if M_kg_s > 0 else 0.0
    DF = 0.15 * LF if LF > 0 else 0.0

    def tau(r: float) -> float:
        inside = r * r + DF * DF - LF / 2.0
        inside = max(0.0, inside)
        return math.exp(-7e-4 * math.sqrt(inside))

    def fq(r: float) -> float:
        if LF <= 0:
            return 0.0
        a = (DF / LF) + 0.5
        b = (r / LF)
        return a / (4.0 * ((a * a + b * b) ** 1.5))

    # Таблица расстояний для отчёта/графиков
    r_grid = [0, 1, 2, 3, 5] + list(range(10, 101, 5)) + [125, 150, 200]

    rows = []
    for r in r_grid:
        t = tau(float(r))
        f = fq(float(r))
        q = Ef_kw_m2 * f * t
        rows.append({
            "r_m": float(r),
            "tau": float(t),
            "Fq": float(f),
            "q_kw_m2": float(q),
        })

    thresholds = [1.4, 4.2, 7.0, 10.5]
    zones = []

    # Ищем расстояние пересечения q(r) с каждым порогом
    for thr in thresholds:
        dist = None
        for i in range(len(rows) - 1):
            r0, q0 = rows[i]["r_m"], rows[i]["q_kw_m2"]
            r1, q1 = rows[i + 1]["r_m"], rows[i + 1]["q_kw_m2"]

            if (q0 - thr) == 0:
                dist = r0
                break

            if (q0 - thr) * (q1 - thr) < 0:
                tlin = (thr - q0) / (q1 - q0)
                dist = r0 + tlin * (r1 - r0)
                break

        zones.append({
            "q_thr_kw_m2": thr,
            "r_m": None if dist is None else round(dist, 1),
        })

    return {
        "params": {
            "M_kg_s": float(M_kg_s),
            "LF_m": float(LF),
            "DF_m": float(DF),
            "Ef_kw_m2": float(Ef_kw_m2),
        },
        "table": rows,
        "zones": zones,
    }
