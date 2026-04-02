# app/pipeline/runner.py
from __future__ import annotations

from typing import Any, Dict

from app.core.calcs.common.wind import calc_wind_zone
from app.core.context import CalculationContext
from app.core.fuels import get_fuel
from app.core.models import POUO, Project, PipeRow
from app.domain.registry import get_scenario
from app.pipeline.config import EngineConfig
from app.pipeline.models import (
    POUOInput, POUOResult, ProjectInput, ProjectResult, ScenarioResult,
)


# ── Выбор аварийного участка ──────────────────────────────────────────────────

def _select_accident_pipe(pipes: list[PipeRow]) -> PipeRow | None:
    for pipe in pipes:
        if getattr(pipe, "is_accident", False):
            return pipe
    return pipes[0] if pipes else None


# ── Построение входных данных для TVS ────────────────────────────────────────

def _cst_from_k(k: float) -> float:
    return 100.0 / (1.0 + 4.84 * k)


def _build_tvs_inputs(
    pouo: POUOInput,
    cfg: EngineConfig,
) -> Dict[str, Any]:
    """
    Транслирует POUOInput + EngineConfig → словарь inputs для TVSExplosionScenario.
    Вся логика подготовки данных сосредоточена здесь — не в сценарии и не в engine.
    """
    acc = _select_accident_pipe(pouo.pipes)
    if acc is None:
        raise ValueError("Нет труб для расчёта.")

    d_m = float(acc.diameter_mm) / 1000.0
    if d_m <= 0:
        raise ValueError("Некорректный диаметр аварийного участка.")

    p_pipe = float(getattr(acc, "pressure_kpa", 0.0) or 0.0)
    P_up_kpa = p_pipe if p_pipe > 0 else float(pouo.inputs.get("P0_kpa", 0.0) or 0.0)
    t_shutoff_s = float(pouo.inputs.get("t_shutoff_s", 0.0) or 0.0)

    if P_up_kpa <= 0 or t_shutoff_s <= 0:
        raise ValueError("Необходимо задать P0_kpa и t_shutoff_s.")

    pipes_data = [
        {"r_m": float(pr.diameter_mm) / 2000.0, "L_m": float(pr.length_m)}
        for pr in pouo.pipes
    ]

    Cst = _cst_from_k(2.0)  # стехиометрия для метана

    return {
        "meta": {
            "scenario_id": f"TVS_{pouo.code}",
            "notes": pouo.title,
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
            "C_g_kg_m3": Cst,
        },
        "release": {
            "orifice_d_m": d_m,
            "mu": cfg.mu_orifice,
            "psi": cfg.psi_critical,
            "Pg_Pa": float(P_up_kpa) * 1000.0,
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


# ── Главные функции ───────────────────────────────────────────────────────────

def run_pouo(pouo: POUOInput, cfg: EngineConfig | None = None) -> POUOResult:
    """
    Запускает все расчётные сценарии для одного ПООУ.

    Для natgas (outdoor):
      tvs_explosion → jet_fire → fireball
    """
    cfg = cfg or EngineConfig()
    result = POUOResult(pouo_input=pouo)
    fuel = get_fuel(pouo.fuel_id)

    if pouo.is_indoor:
        ctx = CalculationContext(inputs=pouo.inputs)
        result.scenarios["indoor"] = ScenarioResult(
            scenario_type="indoor",
            ctx=ctx,
            error="Indoor-сценарий пока не реализован.",
        )
        return result

    if not pouo.pipes:
        ctx = CalculationContext(inputs=pouo.inputs)
        result.scenarios["error"] = ScenarioResult(
            scenario_type="error",
            ctx=ctx,
            error="Нет труб для расчёта.",
        )
        return result

    if fuel.id != "natgas":
        ctx = CalculationContext(inputs=pouo.inputs)
        result.scenarios["skip"] = ScenarioResult(
            scenario_type="skip",
            ctx=ctx,
            error=f"Расчёт реализован только для natgas (выбрано: {fuel.id}).",
        )
        return result

    # ── natgas outdoor ────────────────────────────────────────────────────────
    try:
        tvs_inputs = _build_tvs_inputs(pouo, cfg)
    except ValueError as exc:
        ctx = CalculationContext(inputs=pouo.inputs)
        result.scenarios["error"] = ScenarioResult(
            scenario_type="error", ctx=ctx, error=str(exc)
        )
        return result

    # 1. ТВС-взрыв
    tvs_result = get_scenario("tvs_explosion").run(tvs_inputs)
    result.scenarios["tvs_explosion"] = tvs_result

    if not tvs_result.ok:
        return result

    ctx = tvs_result.ctx
    m_dot = float(ctx.intermediate.get("m_dot_kg_s", 0.0) or 0.0)
    mg = float(ctx.intermediate.get("Mg_kg", 0.0) or 0.0)

    # Ветровые зоны — зависят от m_dot, хранятся в том же ctx
    ctx.results["wind_zones"] = {
        "L_wind1_m": calc_wind_zone(m_dot, 1.0, 25.0),
        "L_wind3_m": calc_wind_zone(m_dot, 3.0, 25.0),
        "r0_wind1_m": calc_wind_zone(m_dot, 1.0, 12.5),
        "r0_wind3_m": calc_wind_zone(m_dot, 3.0, 12.5),
    }

    # 2. Факельное горение
    result.scenarios["jet_fire"] = get_scenario("jet_fire").run({"m_dot_kg_s": m_dot})

    # 3. Огненный шар
    result.scenarios["fireball"] = get_scenario("fireball").run({"m_kg": mg})

    return result


def run_project(
    project: ProjectInput,
    cfg: EngineConfig | None = None,
) -> ProjectResult:
    """Запускает расчёт для всего проекта последовательно."""
    cfg = cfg or EngineConfig()
    pr = ProjectResult(project_input=project)
    for pouo in project.pouos:
        pr.pouo_results.append(run_pouo(pouo, cfg))
    return pr


# ── Конвертеры legacy-моделей ─────────────────────────────────────────────────

def pouo_to_input(p: POUO) -> POUOInput:
    """Конвертирует legacy POUO → POUOInput."""
    return POUOInput(
        code=p.code,
        title=p.title,
        fuel_id=p.fuel_id,
        is_indoor=p.is_indoor,
        inputs=dict(p.inputs),
        pipes=list(p.pipes),
    )


def project_to_input(project: Project) -> ProjectInput:
    """Конвертирует legacy Project → ProjectInput."""
    return ProjectInput(
        name=project.name,
        object_name=project.object_name,
        address=project.address,
        pouos=[pouo_to_input(p) for p in project.pouos],
    )
