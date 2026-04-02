from __future__ import annotations

import math
from typing import Dict, Any

from app.core.calcs.common.probit import probit_to_percent


def calc_fireball_by_M(*, m_kg: float, Ef_kw_m2: float = 80.0) -> Dict[str, Any]:
    """
    Расчёт «огненного шара» по суммарной массе выброса m (п. 7.2 методики).

    Формулы:
      Ds = 5,33 × m^0,327        — эффективный диаметр, м
      H  = Ds / 2                — высота центра шара, м
      ts = 0,92 × m^0,303        — длительность существования, с

      τ(r)  = exp(−7·10⁻⁴ · √(r² + H² − Ds/2))
      Fq(r) = (H/Ds + 0,5) / (4 · ((H/Ds + 0,5)² + (r/Ds)²)^1,5)
      q(r)  = Ef · Fq · τ                              [кВт/м²]

      Pr(r) = −12,8 + 2,56 · ln(ts · q(r)^(4/3))      [пробит ожогов]

    Зоны поражения строятся по порогам q: 1,4 / 4,2 / 7,0 / 10,5 кВт/м².
    """
    if m_kg <= 0:
        return {"skip_reason": "m_kg ≤ 0, огненный шар не рассчитывается."}

    Ds = 5.33 * (m_kg ** 0.327)
    H  = Ds / 2.0
    ts = 0.92 * (m_kg ** 0.303)

    # Постоянная часть формулы Fq: a = H/Ds + 0.5 = 1.0 для шара с H = Ds/2
    a = H / Ds + 0.5

    def _tau(r: float) -> float:
        inside = r * r + H * H - Ds / 2.0
        return math.exp(-7e-4 * math.sqrt(max(0.0, inside)))

    def _fq(r: float) -> float:
        if Ds <= 0:
            return 0.0
        b = r / Ds
        return a / (4.0 * ((a * a + b * b) ** 1.5))

    def _probit_fb(q_kw: float) -> float | None:
        """Пробит поражения тепловым излучением: Pr = −12,8 + 2,56·ln(ts·q^(4/3))."""
        if q_kw <= 0 or ts <= 0:
            return None
        val = ts * (q_kw ** (4.0 / 3.0))
        if val <= 0:
            return None
        return -12.8 + 2.56 * math.log(val)

    # Сетка расстояний: 0..100 как в шаблоне, плюс запас до 200 м
    r_grid = [0, 1, 2, 3, 5] + list(range(10, 101, 10)) + [125, 150, 175, 200]

    rows = []
    for r in r_grid:
        t  = _tau(float(r))
        f  = _fq(float(r))
        q  = Ef_kw_m2 * f * t
        pr = _probit_fb(q)
        rows.append({
            "r_m":     float(r),
            "tau":     float(t),
            "Fq":      float(f),
            "q_kw_m2": float(q),
            "Pr":      pr,
            "prob":    probit_to_percent(pr),
        })

    # Поиск радиусов для каждого порогового значения интенсивности
    thresholds = [1.4, 4.2, 7.0, 10.5]
    zones = []
    for thr in thresholds:
        dist = None
        for i in range(len(rows) - 1):
            r0, q0 = rows[i]["r_m"],     rows[i]["q_kw_m2"]
            r1, q1 = rows[i + 1]["r_m"], rows[i + 1]["q_kw_m2"]
            if abs(q0 - thr) < 1e-9:
                dist = r0
                break
            if (q0 - thr) * (q1 - thr) < 0:
                frac = (thr - q0) / (q1 - q0)
                dist = r0 + frac * (r1 - r0)
                break
        zones.append({
            "q_thr_kw_m2": thr,
            "r_m": None if dist is None else round(dist, 1),
        })

    return {
        "params": {
            "m_kg":     round(m_kg, 2),
            "Ds_m":     round(Ds,   2),
            "H_m":      round(H,    2),
            "ts_s":     round(ts,   2),
            "Ef_kw_m2": float(Ef_kw_m2),
        },
        "table": rows,
        "zones": zones,
    }
