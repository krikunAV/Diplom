# app/core/engine.py
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Dict, Any

from app.core.models import Project, POUO, PipeRow
from app.core.fuels import get_fuel
from app.core.calcs.tvs_pipeline import calc_tvs_pipeline


@dataclass
class EngineConfig:
    # Атмосфера / константы
    p0_pa: float = 101325.0
    c0_m_s: float = 330.0

    # Методика расхода
    psi_critical: float = 0.7
    mu_orifice: float = 0.8
    T_gas_K: float = 293.0
    R0_natgas: float = 486.0       # Дж/(кг·К) как в твоём отчёте
    rho_natgas_n: float = 0.7      # кг/м3 как в отчёте

    # Коэффициент участия массы в облаке
    Z_cloud: float = 0.5

    # ТВС
    tvs_range_id: int = 5
    tvs_sigma: float = 7.0
    tvs_max_r_m: float = 200.0

    # Энергетика
    beta_natgas: float = 1.14
    eud0_base_j_per_kg: float = 44e6

    # Временно фиксируем как в примере
    fuel_class_default: int = 4
    space_kind_default: str = "type3"

    # Прочее
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


def _cst_from_k(k: float) -> float:
    # Cст = 100 / (1 + 4.84 * k)
    return 100.0 / (1.0 + 4.84 * k)


def _calc_jetfire_by_M(*, M_kg_s: float, K: float = 12.5, Ef_kw_m2: float = 80.0) -> Dict[str, Any]:
    """
    Упрощённый расчёт факельного горения:
      Lf = K * M^0.4
      Df = 0.15 * Lf

    Далее считаем q(r) и зоны по q = 1.4 / 4.2 / 7 / 10.5 кВт/м2.
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


def _build_tvs_inputs_for_natgas(
    *,
    p: POUO,
    acc: PipeRow,
    P_up_kpa: float,
    t_shutoff_s: float,
    cfg: EngineConfig,
) -> Dict[str, Any]:
    """
    Собирает inputs под новый CONTEXT_SPEC для natgas.
    """
    d_m = float(acc.diameter_mm) / 1000.0

    pipes_data = []
    for pr in p.pipes:
        d_pipe_m = float(pr.diameter_mm) / 1000.0
        pipes_data.append({
            "r_m": d_pipe_m / 2.0,
            "L_m": float(pr.length_m),
        })

    P_r_pa = float(P_up_kpa) * 1000.0

    # Пока оставляем как в твоём примере.
    # Позже можно заменить на нормальные единицы/справочные данные.
    k_stoich = 2.0
    Cst = _cst_from_k(k_stoich)
    Cg = Cst

    inputs = {
        "meta": {
            "scenario_id": f"TVS_{p.code}",
            "notes": p.title,
        },
        "env": {
            "P0_Pa": cfg.p0_pa,
            "C0_mps": cfg.c0_m_s,
            "wind_mps": 1.0,
        },
        "substance": {
            "rho_gas_kg_m3": cfg.rho_natgas_n,
            "Eud0_J_kg": cfg.eud0_base_j_per_kg,
            "beta": cfg.beta_natgas,
            "sigma": cfg.tvs_sigma,
            "C_st_kg_m3": Cst,
            "C_g_kg_m3": Cg,
        },
        "release": {
            "orifice_d_m": d_m,
            "mu": cfg.mu_orifice,
            "psi": cfg.psi_critical,
            "Pg_Pa": P_r_pa,
            "T_K": cfg.T_gas_K,
            "R0_J_kgK": cfg.R0_natgas,
            "t_shutoff_s": t_shutoff_s,
        },
        "isolated_section": {
            "P2_kPa": float(P_up_kpa),
            "pipes": pipes_data,
        },
        "cloud": {
            "Z": cfg.Z_cloud,
            "cloud_model": "open_area",
        },
        "shockwave": {
            "r_grid_m": [0, 1, 2, 3, 5] + list(range(10, 101, 5)) + [125, 150, 200],
            "explosion_mode": "deflagration",
            "range_id": cfg.tvs_range_id,
        },
    }
    return inputs

def _build_tvs_table_from_ctx(ctx) -> list[dict]:
    """
       Собирает удобную табличную форму для Word/UI:
      r, Rx, Px, Ix, deltaP_Pa, deltaP_kPa, Iplus_Pa_s
    """
    r_grid = ctx.results.get("r_grid_m", [])
    dP = ctx.results.get("dP_Pa", [])
    Iplus = ctx.results.get("Iplus_Pa_s", [])

    Rx = ctx.intermediate.get("Rx", [])
    Px = ctx.intermediate.get("Px", [])
    Ix = ctx.intermediate.get("Ix", [])

    n = min(len(r_grid), len(dP), len(Iplus), len(Rx), len(Px), len(Ix))

    rows = []
    for i in range(n):
        rows.append({
            "r_m": float(r_grid[i]),
            "Rx": float(Rx[i]),
            "Px": float(Px[i]),
            "Ix": float(Ix[i]),
            "deltaP_Pa": float(dP[i]),
            "deltaP_kPa": float(dP[i]) / 1000.0,
            "Iplus_Pa_s": float(Iplus[i]),
        })
    return rows





def compute_for_pouo(p: POUO, cfg: EngineConfig | None = None) -> None:
    cfg = cfg or EngineConfig()

    # всегда считаем заново
    p.results = {}

    fuel = get_fuel(p.fuel_id)
    fuel_id = fuel.id

    p.results["meta"] = {
        "fuel_id_norm": fuel_id,
        "fuel_title": fuel.title,
        "is_indoor": bool(p.is_indoor),
        "code": p.code,
        "title": p.title,
    }

    # indoor пока только сохраняем
    if p.is_indoor:
        p.results["room"] = {
            "V_room_m3": float(p.inputs.get("V_room_m3", 0.0) or 0.0),
            "P0_kpa": float(p.inputs.get("P0_kpa", 0.0) or 0.0),
            "t_shutoff_s": float(p.inputs.get("t_shutoff_s", 0.0) or 0.0),
        }
        p.results["skip"] = "Расчёт indoor-сценария пока не подключён к новому pipeline."
        return

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

    # ---------------- NATGAS ----------------
    if fuel_id == "natgas":
        try:
            inputs = _build_tvs_inputs_for_natgas(
                p=p,
                acc=acc,
                P_up_kpa=P_up_kpa,
                t_shutoff_s=t_shutoff_s,
                cfg=cfg,
            )

            ctx = calc_tvs_pipeline(inputs)

            # release-сводка для UI/Word
            p.results["release"] = {
                "accident_pipe": acc.name,
                "P_up_kpa": float(P_up_kpa),
                "d_hole_mm": float(acc.diameter_mm),
                "t_shutoff_s": float(t_shutoff_s),

                "F_m2": ctx.intermediate.get("F_m2"),
                "v_g_m3_kg": ctx.intermediate.get("v_g_m3_kg"),
                "m_dot_kg_s": ctx.intermediate.get("m_dot_kg_s"),
                "M1T_kg": ctx.intermediate.get("M1T_kg"),
                "sum_r2L_m3": ctx.intermediate.get("sum_r2L_m3"),
                "V2T_m3": ctx.intermediate.get("V2T_m3"),
                "M2T_kg": ctx.intermediate.get("M2T_kg"),
                "Mg_kg": ctx.intermediate.get("Mg_kg"),
                "m_cloud_kg": ctx.intermediate.get("m_cloud_kg"),
                "Eud_J_kg": ctx.intermediate.get("Eud_J_kg"),
                "E_concentration_correction": ctx.intermediate.get("E_concentration_correction"),
                "E_J": ctx.intermediate.get("E_J"),

                # совместимость со старым UI
                "G_kg_s": ctx.intermediate.get("m_dot_kg_s"),
                "m_release_kg": ctx.intermediate.get("M1T_kg"),
                "P2_kpa": float(P_up_kpa),
                "d_m": float(d_m),
                "R0_J_kgK": float(cfg.R0_natgas),
                "T_K": float(cfg.T_gas_K),
                "rho_n_kg_m3": float(cfg.rho_natgas_n),
                "Z": float(cfg.Z_cloud),
            }

            # TVS
            p.results["tvs_explosion"] = {
                "inputs": ctx.inputs,
                "intermediate": ctx.intermediate,
                "results": ctx.results,
                "logs": ctx.logs,
                "table": _build_tvs_table_from_ctx(ctx),
            }

            # jet fire пока оставляем отдельным быстрым расчётом
            m_dot = float(ctx.intermediate.get("m_dot_kg_s", 0.0) or 0.0)
            p.results["jet_fire"] = _calc_jetfire_by_M(M_kg_s=m_dot)

            # fireball для natgas не считаем
            p.results["fireball"] = {
                "skip_reason": "Для природного газа (газопровод) огненный шар обычно не рассчитывают."
            }

        except Exception as e:
            p.results["error"] = str(e)

        return

    # ---------------- остальные топлива ----------------
    p.results["release"] = {
        "skip_reason": "Эта часть методики сейчас реализована только для природного газа (natgas)."
    }
    p.results["jet_fire"] = {
        "skip_reason": "Будет реализовано по методике для выбранного топлива."
    }
    p.results["fireball"] = {
        "skip_reason": "Будет реализовано по методике для выбранного топлива."
    }
    p.results["tvs_explosion"] = {
        "skip_reason": "ТВС-взрыв пока реализован для natgas."
    }


def compute_project(project: Project, cfg: EngineConfig | None = None) -> None:
    cfg = cfg or EngineConfig()
    for p in project.pouos:
        compute_for_pouo(p, cfg)