# app/core/calcs/fireball.py
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Dict, Optional

import matplotlib.pyplot as plt


FIREBALL_THRESHOLDS_KW_M2 = [1.4, 4.2, 7.0, 10.5]

FIREBALL_ZONE_TEXT = {
    1.4: "Без негативных последствий в течение длительного времени",
    4.2: "Безопасно для человека в брезентовой одежде",
    7.0: "Непереносимая боль через 3-5 с; ожог 1 ст. через 6-8 с; ожог 2 ст. через 12-16 с",
    10.5: "Непереносимая боль через 20-30 с; ожог 1 ст. через 15-20 с; ожог 2 ст. через 30-40 с",
}


@dataclass
class FireballResult:
    fuel_id: str
    fuel_title: str
    m_kg: float
    Ds_m: float
    H_m: float
    ts_s: float
    Ef_kw_m2: float
    table_rows: List[Dict[str, float]]
    zones_rows: List[Dict[str, object]]
    chart_path: str


def _interp_clamped(x: float, xs: List[float], ys: List[float]) -> float:
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(len(xs) - 1):
        x0, x1 = xs[i], xs[i + 1]
        if x0 <= x <= x1:
            y0, y1 = ys[i], ys[i + 1]
            t = (x - x0) / (x1 - x0)
            return y0 + t * (y1 - y0)
    return ys[-1]


def select_Ef_kw_m2(fuel_id: str, Ds_m: float) -> float:
    ds = [10, 20, 30, 40, 50]
    table = {
        "natgas": [80, 80, 80, 80, 80],
        "lpg":    [80, 63, 50, 43, 40],
        "diesel": [40, 32, 25, 21, 18],
    }
    ys = table.get(fuel_id, table["natgas"])
    d_eff = max(10.0, float(Ds_m))
    return float(_interp_clamped(d_eff, ds, ys))


def _tau(r_m: float, H_m: float, Ds_m: float) -> float:
    inside = r_m**2 + H_m**2 - Ds_m / 2.0
    inside = max(0.0, inside)
    return math.exp(-7e-4 * math.sqrt(inside))


def _fq(r_m: float, H_m: float, Ds_m: float) -> float:
    if Ds_m <= 0:
        return 0.0
    a = (H_m / Ds_m) + 0.5
    b = (r_m / Ds_m)
    return a / (4.0 * ((a * a + b * b) ** 1.5))


def _build_auto_r_grid() -> List[int]:
    return [0, 1, 2, 3, 5, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90, 100]


def _extend_grid_until_below_threshold(*, Ds: float, H: float, Ef: float, grid: List[int], threshold: float = 1.4, step: int = 10, r_cap: int = 2000) -> List[int]:
    def q_at(r: float) -> float:
        return Ef * _fq(r, H, Ds) * _tau(r, H, Ds)

    r = float(grid[-1])
    while q_at(r) >= threshold and r < r_cap:
        r += step
        grid.append(int(r))
    return grid


def _find_crossing_distance(rows: List[Dict[str, float]], threshold: float) -> Optional[float]:
    for i in range(len(rows) - 1):
        r0 = float(rows[i]["r_m"])
        q0 = float(rows[i]["q_kw_m2"])
        r1 = float(rows[i + 1]["r_m"])
        q1 = float(rows[i + 1]["q_kw_m2"])

        if q0 == threshold:
            return r0
        if q1 == threshold:
            return r1
        if (q0 - threshold) * (q1 - threshold) < 0:
            t = (threshold - q0) / (q1 - q0)
            return r0 + t * (r1 - r0)
    return None


def _save_chart(rows: List[Dict[str, float]], out_path: str) -> str:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    xs = [float(row["r_m"]) for row in rows]
    ys = [float(row["q_kw_m2"]) for row in rows]

    plt.figure()
    plt.plot(xs, ys)
    plt.xlabel("r, м")
    plt.ylabel("q, кВт/м²")
    plt.grid(True)
    plt.title("График зависимости интенсивности теплового излучения «огненного шара» q от расстояния до центра облака")
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close()
    return out_path


def calc_fireball(
    *,
    fuel_id: str,
    fuel_title: str,
    m_kg: float,
    chart_dir: str = "out/charts",
    chart_name: str = "fireball.png",
    threshold_stop_kw_m2: float = 1.4,
) -> FireballResult:
    if m_kg <= 0:
        raise ValueError("m_kg должен быть > 0")

    Ds = 5.33 * (float(m_kg) ** 0.327)
    H = Ds / 2.0
    ts = 0.92 * (float(m_kg) ** 0.303)

    Ef = select_Ef_kw_m2(fuel_id, Ds)

    r_grid = _build_auto_r_grid()
    r_grid = _extend_grid_until_below_threshold(Ds=Ds, H=H, Ef=Ef, grid=r_grid, threshold=threshold_stop_kw_m2)

    table_rows: List[Dict[str, float]] = []
    for r in r_grid:
        r_f = float(r)
        tau = _tau(r_f, H, Ds)
        fq = _fq(r_f, H, Ds)
        q = Ef * fq * tau
        table_rows.append({"r_m": r_f, "tau": float(tau), "Fq": float(fq), "q_kw_m2": float(q)})

    table_rows.sort(key=lambda x: x["r_m"])

    # точка пересечения 1.4 для красивой таблицы
    r_star = _find_crossing_distance(table_rows, 1.4)
    if r_star is not None and all(abs(float(row["r_m"]) - float(r_star)) > 1e-6 for row in table_rows):
        tau_s = _tau(float(r_star), H, Ds)
        fq_s = _fq(float(r_star), H, Ds)
        q_s = Ef * fq_s * tau_s
        table_rows.append({"r_m": float(r_star), "tau": float(tau_s), "Fq": float(fq_s), "q_kw_m2": float(q_s)})
        table_rows.sort(key=lambda x: x["r_m"])

    zones_rows: List[Dict[str, object]] = []
    for thr in FIREBALL_THRESHOLDS_KW_M2:
        dist = _find_crossing_distance(table_rows, float(thr))
        zones_rows.append({
            "degree": FIREBALL_ZONE_TEXT.get(float(thr), ""),
            "q_thr_kw_m2": float(thr),
            "r_m": None if dist is None else round(float(dist), 1),
        })

    chart_path = os.path.join(chart_dir, chart_name)
    chart_path = _save_chart(table_rows, chart_path)

    return FireballResult(
        fuel_id=fuel_id,
        fuel_title=fuel_title,
        m_kg=float(m_kg),
        Ds_m=float(Ds),
        H_m=float(H),
        ts_s=float(ts),
        Ef_kw_m2=float(Ef),
        table_rows=table_rows,
        zones_rows=zones_rows,
        chart_path=chart_path,
    )
