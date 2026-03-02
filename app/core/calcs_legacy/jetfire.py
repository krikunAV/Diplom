# app/core/calcs/jetfire.py
from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import List, Dict, Optional, Literal

import matplotlib.pyplot as plt


Phase = Literal["compressed_gas", "lpg_vapor", "lpg_liquid", "diesel_liquid"]

THRESHOLDS = [1.4, 4.2, 7.0, 10.5]
ZONE_TEXT = {
    1.4: "Без негативных последствий в течение длительного времени",
    4.2: "Безопасно для человека в брезентовой одежде",
    7.0: "Непереносимая боль через 3-5 с; ожог 1 ст. через 6-8 с; ожог 2 ст. через 12-16 с",
    10.5: "Непереносимая боль через 20-30 с; ожог 1 ст. через 15-20 с; ожог 2 ст. через 30-40 с",
}

K_BY_PHASE = {
    "compressed_gas": 12.5,
    "lpg_vapor": 13.5,
    "lpg_liquid": 15.0,
    "diesel_liquid": 15.0,
}


@dataclass
class JetFireResult:
    fuel_id: str
    fuel_title: str
    phase: Phase
    P_up_kpa: float
    P_down_kpa: float
    T_K: float
    d_hole_mm: float
    Cd: float
    G_kg_s: float
    LF_m: float
    DF_m: float
    Ef_kw_m2: float
    table_rows: List[Dict[str, float]]
    zones_rows: List[Dict[str, object]]
    chart_path: str


def _gas_props(fuel_id: str, phase: Phase) -> tuple[float, float]:
    if fuel_id == "natgas":
        return 1.30, 518.0
    if fuel_id == "lpg" and phase == "lpg_vapor":
        return 1.13, 188.0
    return 1.30, 300.0


def _liq_density(fuel_id: str, phase: Phase) -> float:
    if fuel_id == "diesel" or phase == "diesel_liquid":
        return 830.0
    if fuel_id == "lpg" and phase == "lpg_liquid":
        return 520.0
    return 800.0


def gas_mass_flow_orifice(*, P_up_kpa: float, P_down_kpa: float, T_K: float, d_hole_mm: float, Cd: float, gamma: float, R_spec: float) -> float:
    if P_up_kpa <= 0 or T_K <= 0 or d_hole_mm <= 0:
        return 0.0

    P1 = P_up_kpa * 1000.0
    P2 = max(P_down_kpa, 1.0) * 1000.0
    A = math.pi * (d_hole_mm / 1000.0) ** 2 / 4.0

    crit = (2.0 / (gamma + 1.0)) ** (gamma / (gamma - 1.0))
    pr = P2 / P1

    if pr <= crit:
        term = math.sqrt(gamma / (R_spec * T_K)) * (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (2.0 * (gamma - 1.0)))
        G = Cd * A * P1 * term
    else:
        term = math.sqrt((2.0 * gamma / (R_spec * T_K * (gamma - 1.0))) * (pr ** (2.0 / gamma) - pr ** ((gamma + 1.0) / gamma)))
        G = Cd * A * P1 * term

    return max(0.0, float(G))


def liquid_mass_flow_orifice(*, P_up_kpa: float, P_down_kpa: float, d_hole_mm: float, Cd: float, rho: float) -> float:
    if P_up_kpa <= 0 or d_hole_mm <= 0 or rho <= 0:
        return 0.0

    P1 = P_up_kpa * 1000.0
    P2 = max(P_down_kpa, 0.0) * 1000.0
    dP = max(P1 - P2, 0.0)

    A = math.pi * (d_hole_mm / 1000.0) ** 2 / 4.0
    m_dot = Cd * A * math.sqrt(2.0 * rho * dP)
    return max(0.0, float(m_dot))


def calc_G_from_pipe(*, fuel_id: str, phase: Phase, P_up_kpa: float, d_inner_mm: float, hole_mode: Literal["full_bore", "fraction"] = "full_bore", hole_fraction: float = 0.2, P_down_kpa: float = 101.3, T_K: float = 293.15, Cd: float = 0.62) -> tuple[float, float]:
    if d_inner_mm <= 0:
        return 0.0, 0.0

    if hole_mode == "fraction":
        d_hole_mm = max(1.0, float(hole_fraction) * float(d_inner_mm))
    else:
        d_hole_mm = float(d_inner_mm)

    if phase in ("diesel_liquid", "lpg_liquid"):
        rho = _liq_density(fuel_id, phase)
        G = liquid_mass_flow_orifice(P_up_kpa=P_up_kpa, P_down_kpa=P_down_kpa, d_hole_mm=d_hole_mm, Cd=Cd, rho=rho)
    else:
        gamma, R_spec = _gas_props(fuel_id, phase)
        G = gas_mass_flow_orifice(P_up_kpa=P_up_kpa, P_down_kpa=P_down_kpa, T_K=T_K, d_hole_mm=d_hole_mm, Cd=Cd, gamma=gamma, R_spec=R_spec)

    return G, d_hole_mm


def _tau(r_m: float, DF_m: float, LF_m: float) -> float:
    inside = r_m**2 + DF_m**2 - LF_m / 2.0
    inside = max(0.0, inside)
    return math.exp(-7e-4 * math.sqrt(inside))


def _fq(r_m: float, DF_m: float, LF_m: float) -> float:
    if LF_m <= 0:
        return 0.0
    a = (DF_m / LF_m) + 0.5
    b = (r_m / LF_m)
    return a / (4.0 * ((a * a + b * b) ** 1.5))


def _auto_grid() -> List[int]:
    return [0, 1, 2, 3, 5, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90, 100]


def _extend_until_q_below(*, DF: float, LF: float, Ef: float, grid: List[int], threshold: float = 1.4, step: int = 10, cap: int = 3000) -> List[int]:
    def q_at(r: float) -> float:
        return Ef * _fq(r, DF, LF) * _tau(r, DF, LF)

    r = float(grid[-1])
    while q_at(r) >= threshold and r < cap:
        r += step
        grid.append(int(r))
    return grid


def _find_crossing(rows: List[Dict[str, float]], thr: float) -> Optional[float]:
    for i in range(len(rows) - 1):
        r0, q0 = float(rows[i]["r_m"]), float(rows[i]["q_kw_m2"])
        r1, q1 = float(rows[i + 1]["r_m"]), float(rows[i + 1]["q_kw_m2"])
        if q0 == thr:
            return r0
        if q1 == thr:
            return r1
        if (q0 - thr) * (q1 - thr) < 0:
            t = (thr - q0) / (q1 - q0)
            return r0 + t * (r1 - r0)
    return None


def _save_chart(rows: List[Dict[str, float]], out_path: str) -> str:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    xs = [float(r["r_m"]) for r in rows]
    ys = [float(r["q_kw_m2"]) for r in rows]
    plt.figure()
    plt.plot(xs, ys)
    plt.xlabel("r, м")
    plt.ylabel("q, кВт/м²")
    plt.grid(True)
    plt.title("График зависимости интенсивности теплового излучения факела q от расстояния до границы зоны горения")
    plt.tight_layout()
    plt.savefig(out_path, dpi=300)
    plt.close()
    return out_path


def calc_jet_fire(
    *,
    fuel_id: str,
    fuel_title: str,
    phase: Phase,
    P_up_kpa: float,
    d_inner_mm: float,
    hole_mode: Literal["full_bore", "fraction"] = "full_bore",
    hole_fraction: float = 0.2,
    P_down_kpa: float = 101.3,
    T_K: float = 293.15,
    Cd: float = 0.62,
    Ef_kw_m2: float = 80.0,
    chart_dir: str = "out/charts",
    chart_name: str = "jetfire.png",
) -> JetFireResult:
    G, d_hole_mm = calc_G_from_pipe(
        fuel_id=fuel_id,
        phase=phase,
        P_up_kpa=P_up_kpa,
        d_inner_mm=d_inner_mm,
        hole_mode=hole_mode,
        hole_fraction=hole_fraction,
        P_down_kpa=P_down_kpa,
        T_K=T_K,
        Cd=Cd,
    )

    K = K_BY_PHASE[phase]
    LF = K * (G ** 0.4) if G > 0 else 0.0
    DF = 0.15 * LF if LF > 0 else 0.0

    grid = _auto_grid()
    if LF > 0:
        grid = _extend_until_q_below(DF=DF, LF=LF, Ef=Ef_kw_m2, grid=grid, threshold=1.4)

    table_rows: List[Dict[str, float]] = []
    for r in grid:
        r_f = float(r)
        tau = _tau(r_f, DF, LF) if LF > 0 else 0.0
        fq = _fq(r_f, DF, LF) if LF > 0 else 0.0
        q = Ef_kw_m2 * fq * tau if LF > 0 else 0.0
        table_rows.append({"r_m": r_f, "tau": float(tau), "Fq": float(fq), "q_kw_m2": float(q)})

    table_rows.sort(key=lambda x: x["r_m"])

    r_star = _find_crossing(table_rows, 1.4)
    if r_star is not None and all(abs(float(rr["r_m"]) - float(r_star)) > 1e-6 for rr in table_rows):
        tau_s = _tau(float(r_star), DF, LF)
        fq_s = _fq(float(r_star), DF, LF)
        q_s = Ef_kw_m2 * fq_s * tau_s
        table_rows.append({"r_m": float(r_star), "tau": float(tau_s), "Fq": float(fq_s), "q_kw_m2": float(q_s)})
        table_rows.sort(key=lambda x: x["r_m"])

    zones_rows: List[Dict[str, object]] = []
    for thr in THRESHOLDS:
        dist = _find_crossing(table_rows, float(thr))
        zones_rows.append({"degree": ZONE_TEXT.get(float(thr), ""), "q_thr_kw_m2": float(thr), "r_m": None if dist is None else round(float(dist), 1)})

    chart_path = os.path.join(chart_dir, chart_name)
    chart_path = _save_chart(table_rows, chart_path)

    return JetFireResult(
        fuel_id=fuel_id,
        fuel_title=fuel_title,
        phase=phase,
        P_up_kpa=float(P_up_kpa),
        P_down_kpa=float(P_down_kpa),
        T_K=float(T_K),
        d_hole_mm=float(d_hole_mm),
        Cd=float(Cd),
        G_kg_s=float(G),
        LF_m=float(LF),
        DF_m=float(DF),
        Ef_kw_m2=float(Ef_kw_m2),
        table_rows=table_rows,
        zones_rows=zones_rows,
        chart_path=chart_path,
    )
