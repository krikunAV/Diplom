# app/core/engine.pyВ
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Dict, Any

from app.core.models import Project, POUO, PipeRow
from app.core.fuels import get_fuel
from app.core.calcs.tvs_pipeline import calc_tvs_pipeline


@dataclass
class EngineConfig:
    # Атмосфера/константы для ТВС
    p0_pa: float = 101325.0
    c0_m_s: float = 330.0

    # Методика расхода (как в твоём отчёте)
    psi_critical: float = 0.7
    mu_orifice: float = 0.8
    T_gas_K: float = 293.0
    R0_natgas: float = 486.0      # Дж/(кг·К) как в отчёте
    rho_natgas_n: float = 0.7     # кг/м3 как в отчёте (н.у.)

    # Коэффициент участия массы в облаке (Z)
    Z_cloud: float = 0.5

    # ТВС режим/параметры как в отчёте
    tvs_range_id: int = 5
    tvs_sigma: float = 7.0
    tvs_max_r_m: float = 200.0

    # Энергетика как в отчёте: Eуд = β * 44e6
    beta_natgas: float = 1.14
    eud0_base_j_per_kg: float = 44e6

    # Выбор класса/типа пространства (пока фиксируем как у тебя в примере)
    fuel_class_default: int = 4
    space_kind_default: str = "type3"

    # Графики
    make_charts: bool = True


def select_accident_pipe(p: POUO) -> Optional[PipeRow]:
    for pipe in (p.pipes or []):
        if getattr(pipe, "is_accident", False):
            return pipe
    return p.pipes[0] if p.pipes else None


def _get_pressure_up_kpa(p: POUO, pipe: PipeRow) -> float:
    p_pipe = float(getattr(pipe, "pressure_kpa", 0.0) or 0.0)
    if p_pipe > 0:
        return p_pipe
    return float(p.inputs.get("P0_kpa", 0.0) or 0.0)


def _critical_mass_flow_natgas(*, P_r_pa: float, d_m: float, cfg: EngineConfig) -> Dict[str, float]:
    """
    По отчёту:
      F = π d² / 4
      Vr = R0*T/Pr
      M = ψ * F * μ * sqrt(Pr / Vr)
    """
    F = math.pi * d_m * d_m / 4.0
    Vr = cfg.R0_natgas * cfg.T_gas_K / max(P_r_pa, 1e-9)
    M = cfg.psi_critical * F * cfg.mu_orifice * math.sqrt(max(P_r_pa, 0.0) / max(Vr, 1e-12))
    return {"F_m2": F, "Vr_m3_kg": Vr, "M_kg_s": M}


def _v2t_after_shutoff(*, P2_kpa: float, pipes: list[PipeRow]) -> Dict[str, float]:
    """
    По отчёту:
      V2T = 0.01 * π * P2 * Σ(r² * L)
    где:
      P2 — кПа,
      r — м (радиус трубы),
      L — м
    """
    s = 0.0
    for pr in pipes:
        d_m = float(pr.diameter_mm) / 1000.0
        r = d_m / 2.0
        L = float(pr.length_m)
        s += (r * r) * L

    V2T = 0.01 * math.pi * float(P2_kpa) * s
    return {"sum_r2L": s, "V2T_m3": V2T}


def _cst_from_k(k: float) -> float:
    # Cст = 100/(1 + 4.84*k)
    return 100.0 / (1.0 + 4.84 * k)


def _calc_jetfire_by_M(*, M_kg_s: float, K: float = 12.5, Ef_kw_m2: float = 80.0) -> Dict[str, Any]:
    """
    Факел как в отчёте:
      Lf = K * M^0.4
      Df = 0.15 * Lf
    Дальше: τ, Fq, q и зоны по q=1.4/4.2/7/10.5
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

    # сетка как в твоём графике/таблице
    r_grid = [0, 1, 2, 3, 5] + list(range(10, 101, 5)) + [125, 150, 200]

    rows = []
    for r in r_grid:
        t = tau(float(r))
        f = fq(float(r))
        q = Ef_kw_m2 * f * t
        rows.append({"r_m": float(r), "tau": float(t), "Fq": float(f), "q_kw_m2": float(q)})

    # зоны
    thresholds = [1.4, 4.2, 7.0, 10.5]
    zones = []
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
        zones.append({"q_thr_kw_m2": thr, "r_m": None if dist is None else round(dist, 1)})

    return {
        "params": {"M_kg_s": float(M_kg_s), "LF_m": float(LF), "DF_m": float(DF), "Ef_kw_m2": float(Ef_kw_m2)},
        "table": rows,
        "zones": zones,
    }


def compute_for_pouo(p: POUO, cfg: EngineConfig | None = None) -> None:
    cfg = cfg or EngineConfig()

    # ✅ всегда считаем "с нуля"
    p.results = {}

    fuel = get_fuel(p.fuel_id)
    fuel_id = fuel.id

    # meta
    p.results["meta"] = {
        "fuel_id_norm": fuel_id,
        "fuel_title": fuel.title,
        "is_indoor": bool(p.is_indoor),
        "code": p.code,
        "title": p.title,
    }

    # indoor: только сохраняем
    if p.is_indoor:
        p.results["room"] = {
            "V_room_m3": float(p.inputs.get("V_room_m3", 0.0) or 0.0),
            "P0_kpa": float(p.inputs.get("P0_kpa", 0.0) or 0.0),
            "t_shutoff_s": float(p.inputs.get("t_shutoff_s", 0.0) or 0.0),
        }
        return

    # если труб нет (POUO1 и т.п.)
    if not p.pipes:
        p.results["skip"] = "Нет труб для расчёта (сценарий без трубопроводов или не заполнено)."
        return

    acc = select_accident_pipe(p)
    if acc is None:
        p.results["error"] = "Нет труб для расчёта."
        return

    P_up_kpa = _get_pressure_up_kpa(p, acc)
    t_shutoff_s = float(p.inputs.get("t_shutoff_s", 0.0) or 0.0)

    if P_up_kpa <= 0 or t_shutoff_s <= 0:
        p.results["error"] = "Нужно задать P0_kpa и t_shutoff_s."
        return

    d_m = float(acc.diameter_mm) / 1000.0
    if d_m <= 0:
        p.results["error"] = "Некорректный диаметр аварийного участка."
        return

    # ---------------- NATGAS: как в отчёте ----------------
    if fuel_id == "natgas":
        P_r_pa = float(P_up_kpa) * 1000.0
        mf = _critical_mass_flow_natgas(P_r_pa=P_r_pa, d_m=d_m, cfg=cfg)
        M_kg_s = float(mf["M_kg_s"])

        # масса до отсечки
        M1T = M_kg_s * t_shutoff_s

        # объём/масса после отсечки
        v2 = _v2t_after_shutoff(P2_kpa=P_up_kpa, pipes=p.pipes)
        V2T = float(v2["V2T_m3"])
        M2T = V2T * cfg.rho_natgas_n

        M2_total = M1T + M2T
        mr = M2_total * cfg.Z_cloud

        # энергия как в отчёте
        Eud = cfg.beta_natgas * cfg.eud0_base_j_per_kg

        # как в отчёте: k=2, Cg=Cst
        k_stoich = 2.0
        Cst = _cst_from_k(k_stoich)
        Cg = Cst

        # release — + совместимость со старой сводкой
        p.results["release"] = {
            # "как в отчёте"
            "accident_pipe": acc.name,
            "P2_kpa": float(P_up_kpa),
            "d_m": float(d_m),
            "F_m2": float(mf["F_m2"]),
            "R0_J_kgK": float(cfg.R0_natgas),
            "T_K": float(cfg.T_gas_K),
            "Vr_m3_kg": float(mf["Vr_m3_kg"]),
            "psi": float(cfg.psi_critical),
            "mu": float(cfg.mu_orifice),
            "M_kg_s": float(M_kg_s),
            "t_shutoff_s": float(t_shutoff_s),
            "M1T_kg": float(M1T),
            "sum_r2L": float(v2["sum_r2L"]),
            "V2T_m3": float(V2T),
            "rho_n_kg_m3": float(cfg.rho_natgas_n),
            "M2T_kg": float(M2T),
            "M2_total_kg": float(M2_total),
            "Z": float(cfg.Z_cloud),
            "mr_kg": float(mr),
            "beta": float(cfg.beta_natgas),
            "Eud_J_kg": float(Eud),
            "k_stoich": float(k_stoich),
            "Cst_vol_percent": float(Cst),
            "Cg_vol_percent": float(Cg),

            # "совместимость" со старой сводкой UI
            "P_up_kpa": float(P_up_kpa),
            "d_hole_mm": float(acc.diameter_mm),
            "G_kg_s": float(M_kg_s),          # в твоём отчёте расход обозначен M, но это тот же кг/с
            "m_release_kg": float(M1T),       # масса до отсечки
            "m_cloud_kg": float(mr),          # масса, участвующая во взрыве (облако)
        }

        # jet fire по M из отчёта
        p.results["jet_fire"] = _calc_jetfire_by_M(M_kg_s=M_kg_s)

        # огненный шар для natgas обычно не считают
        p.results["fireball"] = {"skip_reason": "Для природного газа (газопровод) огненный шар обычно не рассчитывают."}

        # ТВС-взрыв
        tvs = calc_tvs_explosion(
            m_g_kg=mr,
            q_g_j_per_kg=Eud,
            c_g=Cg,
            c_st=Cst,
            fuel_class=cfg.fuel_class_default,
            space_kind=cfg.space_kind_default,
            range_id=cfg.tvs_range_id,
            sigma=cfg.tvs_sigma,
            p0_pa=cfg.p0_pa,
            c0_m_s=cfg.c0_m_s,
            max_r_m=cfg.tvs_max_r_m,
            make_charts=cfg.make_charts,
            chart_dp_path=f"out/charts/tvs_dp_{p.code}.png".replace(" ", "_"),
            chart_imp_path=f"out/charts/tvs_imp_{p.code}.png".replace(" ", "_"),
        )

        # добавим ΔP в кПа для удобства графика/отчёта
        table = []
        for row in tvs.table_rows:
            rr = dict(row)
            rr["deltaP_kPa"] = rr["deltaP_Pa"] / 1000.0
            table.append(rr)

        p.results["tvs_explosion"] = {
            "params": tvs.params,
            "table": table,
            "chart_dp_path": tvs.chart_dp_path,
            "chart_imp_path": tvs.chart_imp_path,
        }

        return

    # ---------------- остальные топлива пока пропускаем ----------------
    p.results["release"] = {"skip_reason": "Эта часть методики сейчас реализована только для природного газа (natgas)."}
    p.results["jet_fire"] = {"skip_reason": "Будет реализовано по методике для выбранного топлива."}
    p.results["fireball"] = {"skip_reason": "Будет реализовано по методике для выбранного топлива."}
    p.results["tvs_explosion"] = {"skip_reason": "ТВС-взрыв пока реализован для natgas."}


def compute_project(project: Project, cfg: EngineConfig | None = None) -> None:
    cfg = cfg or EngineConfig()
    for p in project.pouos:
        compute_for_pouo(p, cfg)