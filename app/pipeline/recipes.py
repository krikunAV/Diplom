# app/pipeline/recipes.py
"""
Рецепты ПООУ — фабрики списков ScenarioConfig.

Правило: runner.py ничего не знает о конкретных сценариях.
Все знания о том, «что запускать и с какими входными данными»,
живут здесь.

Добавить новый рецепт:
  1. написать build_inputs функцию
  2. написать фабрику <name>_scenarios()
  3. добавить ветку в get_recipe()
"""
from __future__ import annotations

import math
from typing import Any, Dict, List

from app.pipeline.config import EngineConfig
from app.pipeline.models import POUOInput, ScenarioConfig
from app.core.models import PipeRow
from app.core.fuels import get_fuel


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
        ScenarioConfig(
            "tvs_explosion",
            _build_tvs_inputs,
            requires=frozenset(),
            provides=frozenset({"m_dot_kg_s", "Mg_kg"}),
        ),
        ScenarioConfig(
            "jet_fire",
            _build_jet_fire_inputs,
            requires=frozenset({"m_dot_kg_s"}),
            provides=frozenset(),
        ),
        ScenarioConfig(
            "fireball",
            _build_fireball_inputs,
            requires=frozenset({"Mg_kg"}),
            provides=frozenset(),
        ),
    ]


# ── Резервуарный парк ─────────────────────────────────────────────────────────

# Справочные величины для текста отчёта ПОУО1 (СУГ) — подставляются в Word;
# пользователь может переопределить через pouo.inputs["lpg"] / ["site"].
_DEFAULT_LPG_REPORT_PROPS: Dict[str, Any] = {
    "equiv_tnt_kg": 10.0,
    "P_vessel_Pa": 1_560_000.0,
    "P_crit_Pa": 4_190_000.0,
    "T_crit_K": 370.0,
    "M_kg_kmol": 44.0,
    "rho_vapor_kg_m3": 1.83,
    "T_calc_C": 20.0,
    "expansion_factor": 250.0,
    "lower_flammability_pct": 7.7,
    "gamma": 1.257,
    "Ef_surface_W_m2": 40_000.0,
    "nozzle_radius_m": 0.23,
}

_DEFAULT_SITE_DISTANCES_M: Dict[str, float] = {
    "dist_kpp_m": 16.0,
    "dist_sklad_m": 24.0,
    "dist_kotelnaya_m": 33.0,
}


def _build_tank_park_inputs(
    pouo: POUOInput,
    cfg: EngineConfig,
    accumulated: dict,
) -> Dict[str, Any]:
    """
    Строит raw_inputs для TankParkScenario из POUOInput.

    Поддерживаемые fuel_id: "diesel", "lpg".
    Не использует pouo.pipes / PipeRow.
    """
    fuel = get_fuel(pouo.fuel_id)

    tank = pouo.inputs.get("tank", {})
    spill = pouo.inputs.get("spill", {})
    fill_fraction = float(tank.get("fill_fraction", 0.8) or 0.8)

    if pouo.fuel_id == "diesel":
        fuel_section: Dict[str, Any] = {
            "id":                    "diesel",
            "rho_liq":               fuel.rho_liq,
            "eud0_j_per_kg":         fuel.eud0_j_per_kg,
            # Константы испарения (ГОСТ К.1) — Pnas в кПа при расчётной температуре
            "Pnas_kpa":              cfg.diesel_Pnas_kpa,
            "M_g_mol":               cfg.diesel_M_g_mol,
            # Параметры пожара пролива
            "Ef_pool_kw_m2":         cfg.diesel_Ef_pool_kw_m2,
            "burn_rate_kg_m2_s":     cfg.diesel_burn_rate_kg_m2_s,
            # Параметры огненного шара (ГОСТ Б.1, дизель)
            "Ef_fireball_kw_m2":     cfg.diesel_Ef_fireball_kw_m2,
        }
        substance: Dict[str, Any] = {
            "sigma":    cfg.sigma_diesel,
            "beta":     1.0,
            # Для run_shockwave нужны C_st и C_g — устанавливаем одинаковыми
            # → correction = 1 (консервативно, METHODOLOGY_7_1_7_3.md §7.1.10)
            "rho_gas_kg_m3":  0.7,     # не используется в TVS tank_park
            "Eud0_J_kg":      fuel.eud0_j_per_kg,
            "C_st_kg_m3":     0.064,
            "C_g_kg_m3":      0.064,
        }
    else:  # lpg
        fuel_section = {
            "id":                "lpg",
            "rho_liq":           fuel.rho_liq,
            "eud0_j_per_kg":     fuel.eud0_j_per_kg,
            # Параметры факела (ГОСТ Б.1, пропан)
            "Ef_jet_kw_m2":      cfg.lpg_Ef_jet_kw_m2,
            # Параметры огненного шара BLEVE (TNO Green Book гл. 6)
            "Ef_fireball_kw_m2": cfg.lpg_Ef_fireball_kw_m2,
        }
        substance = {
            "sigma": cfg.sigma_lpg,
            "beta":  1.0,
        }

    # Плотность персонала (для run_people_exposure)
    exposure_raw = pouo.inputs.get("exposure", {}) or {}
    exposure_section: Dict[str, Any] = {
        "people_density_per_ha": float(exposure_raw.get("people_density_per_ha", 0.0)),
    }

    out: Dict[str, Any] = {
        "meta": {
            "scenario_id": f"TANKPARK_{pouo.code}",
            "fuel_id":     pouo.fuel_id,
            "notes":       pouo.title,
        },
        "tank": {
            "volume_m3":     float(tank.get("volume_m3", 0.0)),
            "count":         int(tank.get("count", 1)),
            "fill_fraction": fill_fraction,
        },
        "spill": {
            "area_m2":            float(spill.get("area_m2", 0.0)),
            "duration_s":         float(spill.get("duration_s", 3600.0)),
            "eta":                1.0,                      # без ветра
            "flash_fraction":     float(spill.get("flash_fraction", cfg.lpg_flash_fraction)),
            "pool_evap_fraction": float(spill.get("pool_evap_fraction", cfg.lpg_pool_evap_fraction)),
            "peak_duration_s":    float(spill.get("peak_duration_s", 2.5)),
        },
        "fuel":      fuel_section,
        "substance": substance,
        "cloud": {
            "Z": cfg.Z_tank,
        },
        "env": {
            "P0_Pa":   cfg.p0_pa,
            "C0_mps":  cfg.c0_m_s,
        },
        # Нужно для run_shockwave (только для diesel):
        "shockwave": {
            "r_grid_m":      [0, 1, 2, 3, 5] + list(range(10, 101, 5)) + [125, 150, 200],
            "explosion_mode": "deflagration",
            "range_id":      cfg.tvs_range_id,
        },
        "exposure": exposure_section,
    }

    if pouo.fuel_id == "lpg":
        user_lpg = dict(pouo.inputs.get("lpg") or {})
        out["lpg"] = {
            **_DEFAULT_LPG_REPORT_PROPS,
            "rho_liq_kg_m3": float(fuel.rho_liq),
            **user_lpg,
        }
        user_site = dict(pouo.inputs.get("site") or {})
        merged_site = dict(_DEFAULT_SITE_DISTANCES_M)
        for k, v in user_site.items():
            try:
                merged_site[k] = float(v)
            except (TypeError, ValueError):
                pass
        out["site"] = merged_site

    return out


def tank_park_scenarios() -> List[ScenarioConfig]:
    """Рецепт для резервуарного парка (diesel или lpg)."""
    return [
        ScenarioConfig(
            "tank_park",
            _build_tank_park_inputs,
            requires=frozenset(),
            provides=frozenset({"Mg_kg"}),
        ),
    ]


# ── Реестр рецептов ───────────────────────────────────────────────────────────

def get_recipe(
    fuel_id: str,
    is_indoor: bool,
    scenario_code: str = "",
) -> List[ScenarioConfig]:
    """
    Возвращает список ScenarioConfig для заданного ПООУ.

    Приоритет проверок:
      1. scenario_code == "POUO1"  → резервуарный парк
      2. outdoor natgas            → трубопроводный газ
      3. всё остальное             → пустой список (заглушка)
    """
    if scenario_code == "POUO1":
        return tank_park_scenarios()

    if not is_indoor and fuel_id == "natgas":
        return natgas_outdoor_scenarios()

    # Заглушка: пустой список — runner вернёт пустой POUOResult
    return []
