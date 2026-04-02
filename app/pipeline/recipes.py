# app/pipeline/recipes.py
"""
Рецепты ПООУ — фабрики списков ScenarioConfig.

Правило: runner.py ничего не знает о конкретных сценариях.
Все знания о том, «что запускать и с какими входными данными»,
живут здесь.

Добавить новый рецепт (например, LPG outdoor):
  1. написать функцию lpg_outdoor_scenarios()
  2. зарегистрировать её в RECIPES
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

from app.pipeline.config import EngineConfig
from app.pipeline.models import POUOInput, ScenarioConfig
from app.core.models import PipeRow


# ── Вспомогательные функции построения входных данных ─────────────────────────

def _select_accident_pipe(pipes: List[PipeRow]) -> PipeRow | None:
    for pipe in pipes:
        if getattr(pipe, "is_accident", False):
            return pipe
    return pipes[0] if pipes else None


def _cst_from_k(k: float) -> float:
    return 100.0 / (1.0 + 4.84 * k)


# ── Построители raw_inputs для каждого сценария ───────────────────────────────

def _build_tvs_inputs(
    pouo: POUOInput,
    cfg: EngineConfig,
    accumulated: dict,
) -> Dict[str, Any]:
    """
    TVS-взрыв: полный набор входных данных из POUOInput + EngineConfig.
    accumulated не используется — TVS всегда идёт первым.
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
    Cst = _cst_from_k(2.0)

    return {
        "meta": {"scenario_id": f"TVS_{pouo.code}", "notes": pouo.title},
        "env": {"P0_Pa": cfg.p0_pa, "C0_mps": cfg.c0_m_s, "wind_mps": 1.0},
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
        "isolated_section": {"P2_kPa": float(P_up_kpa), "pipes": pipes_data},
        "cloud": {"Z": cfg.Z_cloud, "cloud_model": "open_area"},
        "shockwave": {
            "r_grid_m": [0, 1, 2, 3, 5] + list(range(10, 101, 5)) + [125, 150, 200],
            "explosion_mode": "deflagration",
            "range_id": cfg.tvs_range_id,
        },
    }


def _build_jet_fire_inputs(
    pouo: POUOInput,
    cfg: EngineConfig,
    accumulated: dict,
) -> Dict[str, Any]:
    """
    Факельное горение: использует m_dot из TVS-расчёта через accumulated.
    Нет прямой зависимости от TVSExplosionScenario.
    """
    return {"m_dot_kg_s": float(accumulated.get("m_dot_kg_s", 0.0) or 0.0)}


def _build_fireball_inputs(
    pouo: POUOInput,
    cfg: EngineConfig,
    accumulated: dict,
) -> Dict[str, Any]:
    """
    Огненный шар: использует Mg из TVS-расчёта через accumulated.
    Нет прямой зависимости от TVSExplosionScenario.
    """
    return {"m_kg": float(accumulated.get("Mg_kg", 0.0) or 0.0)}


# ── Рецепты (фабрики списков ScenarioConfig) ──────────────────────────────────

def natgas_outdoor_scenarios() -> List[ScenarioConfig]:
    """
    Рецепт для наружного объекта на природном газе.

    Порядок выполнения важен: TVS идёт первым, так как
    jet_fire и fireball читают m_dot/Mg из accumulated.
    """
    return [
        ScenarioConfig("tvs_explosion", _build_tvs_inputs),
        ScenarioConfig("jet_fire",      _build_jet_fire_inputs),
        ScenarioConfig("fireball",      _build_fireball_inputs),
    ]


# ── Реестр рецептов ───────────────────────────────────────────────────────────

def get_recipe(fuel_id: str, is_indoor: bool) -> List[ScenarioConfig]:
    """
    Возвращает список ScenarioConfig для заданного топлива и типа размещения.
    Добавить новое топливо/тип — добавить ветку здесь.
    """
    if not is_indoor and fuel_id == "natgas":
        return natgas_outdoor_scenarios()

    # Заглушка: пустой список — runner вернёт пустой POUOResult
    return []
