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
from app.core.fuels import get_fuel, normalize_fuel_id


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


def _build_lpg_pipe_tvs_inputs(
    pouo: POUOInput,
    cfg: EngineConfig,
    accumulated: dict,
) -> Dict[str, Any]:
    """
    POUO6: выброс СУГ из наружного трубопровода/установки.

    Отличие от natgas TVS:
    - газовая постоянная и теплота сгорания берутся для СУГ;
    - после общего Mg включается optional lpg_flash branch:
      Mg -> m_flash/m_pool_evap -> m_cloud/E.
    """
    t_shutoff_s = float(pouo.inputs.get("t_shutoff_s", 0.0) or 0.0)
    if t_shutoff_s <= 0:
        raise ValueError("Для POUO6 необходимо задать t_shutoff_s.")

    raw_lpg_pipe = pouo.inputs.get("lpg_pipe") or {}

    def _phase_pressure(phase: str, fallback_key: str, default: float) -> float:
        phase_data = raw_lpg_pipe.get(phase) or {}
        return float(phase_data.get("P", pouo.inputs.get(fallback_key, default)) or 0.0)

    def _phase_pipes(phase: str) -> List[Dict[str, Any]]:
        phase_data = raw_lpg_pipe.get(phase) or {}
        rows = phase_data.get("pipes") or []
        out = []
        for i, row in enumerate(rows, start=1):
            d_mm = float(row.get("diameter_mm", 0.0) or 0.0)
            length_m = float(row.get("length_m", 0.0) or 0.0)
            if d_mm <= 0 or length_m <= 0:
                raise ValueError(
                    f"POUO6: {phase} pipe #{i} должен иметь diameter_mm > 0 и length_m > 0."
                )
            out.append({
                "name": row.get("name", f"{phase} #{i}"),
                "r_m": d_mm / 2000.0,
                "L_m": length_m,
                "diameter_mm": d_mm,
                "length_m": length_m,
                "is_accident": bool(row.get("is_accident", False)),
            })
        return out

    P_liquid_kPa = _phase_pressure("liquid", "P_liquid_kpa", 500.0)
    P_vapor_kPa = _phase_pressure("vapor", "P_vapor_kpa", 30.0)
    liquid_pipes = _phase_pipes("liquid")
    vapor_pipes = _phase_pipes("vapor")

    if P_liquid_kPa <= 0 or P_vapor_kPa <= 0:
        raise ValueError("POUO6: P_liquid и P_vapor должны быть > 0.")
    if not liquid_pipes:
        raise ValueError("POUO6: нужно задать трубы жидкой фазы.")
    if not vapor_pipes:
        raise ValueError("POUO6: нужно задать трубы паровой фазы.")
    accident_count = sum(1 for p in liquid_pipes + vapor_pipes if p["is_accident"])
    if accident_count != 1:
        raise ValueError("POUO6: должен быть выбран ровно один аварийный участок среди liquid и vapor.")

    fuel = get_fuel("lpg")
    Pg_Pa = P_liquid_kPa * 1000.0
    rho_lpg_working = Pg_Pa / (cfg.R0_lpg * cfg.T_gas_K)

    lpg_input = pouo.inputs.get("lpg", {}) or {}
    cst = float(lpg_input.get("C_st_kg_m3", 0.0727) or 0.0727)
    cg = float(lpg_input.get("C_g_kg_m3", cst) or cst)
    # templatePOUO6 далее использует округлённое Eуд = 46 * 10^6 Дж/кг.
    beta = float(lpg_input.get("beta", 1.0) or 1.0)
    flash_fraction = float(lpg_input.get("flash_fraction", cfg.lpg_flash_fraction))
    pool_evap_fraction = float(lpg_input.get("pool_evap_fraction", cfg.lpg_pool_evap_fraction))
    peak_duration_s = float(lpg_input.get("peak_duration_s", 2.5))

    if cst <= 0 or cg <= 0:
        raise ValueError("POUO6: C_st_kg_m3 и C_g_kg_m3 должны быть > 0.")
    if beta <= 0:
        raise ValueError("POUO6: beta должен быть > 0.")
    if not 0 < flash_fraction <= 1:
        raise ValueError("POUO6: flash_fraction должен быть в диапазоне (0, 1].")
    if not 0 <= pool_evap_fraction <= 1:
        raise ValueError("POUO6: pool_evap_fraction должен быть в диапазоне [0, 1].")
    if peak_duration_s <= 0:
        raise ValueError("POUO6: peak_duration_s должен быть > 0.")

    return {
        "meta": {"scenario_id": f"TVS_{pouo.code}", "notes": pouo.title},
        "env": {"P0_Pa": cfg.p0_pa, "C0_mps": cfg.c0_m_s, "wind_mps": 1.0},
        "substance": {
            "rho_gas_kg_m3": rho_lpg_working,
            "Eud0_J_kg": float(lpg_input.get("Eud0_J_kg", 46e6)),
            "beta": beta,
            "sigma": cfg.sigma_lpg,
            "C_st_kg_m3": cst,
            "C_g_kg_m3": cg,
        },
        # release/isolated_section нужны базовому модулю TVS. Для POUO6
        # итоговые Mg/m_cloud/E переопределяются модулем lpg_flash_cloud_energy
        # по двум независимым фазовым системам из inputs["lpg_pipe"].
        "release": {
            "orifice_d_m": 2.0 * next((p["r_m"] for p in liquid_pipes if p["is_accident"]), liquid_pipes[0]["r_m"]),
            "mu": cfg.mu_orifice,
            "psi": cfg.psi_critical,
            "Pg_Pa": Pg_Pa,
            "T_K": cfg.T_gas_K,
            "R0_J_kgK": cfg.R0_lpg,
            "t_shutoff_s": t_shutoff_s,
        },
        "isolated_section": {"P2_kPa": P_liquid_kPa, "pipes": liquid_pipes + vapor_pipes},
        "cloud": {"Z": cfg.Z_cloud, "cloud_model": "lpg_outdoor_pipe"},
        "lpg_flash": {
            "duration_s": t_shutoff_s,
            "flash_fraction": flash_fraction,
            "pool_evap_fraction": pool_evap_fraction,
            "peak_duration_s": peak_duration_s,
        },
        "lpg_pipe": {
            "liquid": {"P_kPa": P_liquid_kPa, "pipes": liquid_pipes},
            "vapor": {"P_kPa": P_vapor_kPa, "pipes": vapor_pipes},
            "constants": {
                "rho_vapor_kg_m3": float(lpg_input.get("rho_vapor_kg_m3", 1.8332)),
                "rho_liq_kg_m3": float(lpg_input.get("rho_liq_kg_m3", fuel.rho_liq)),
                "vapor_yield_m3_kg": float(lpg_input.get("vapor_yield_m3_kg", 0.51)),
                "C_st_kg_m3": cst,
                "energy_multiplier": float(lpg_input.get("energy_multiplier", 2.0)),
                "P_crit_Pa": float(lpg_input.get("P_crit_Pa", 4_190_000.0)),
                "T_crit_K": float(lpg_input.get("T_crit_K", 370.0)),
                "T_liq_K": float(lpg_input.get("T_liq_K", cfg.T_gas_K)),
                "gamma": float(lpg_input.get("gamma", 1.257)),
                # Раздел 11 templatePOUO6 использует пропановую M=0.044 кг/моль
                # и R=8.31 Дж/(моль*K), то есть R0≈188.9 Дж/(кг*K).
                "R0_J_kgK": float(lpg_input.get("R0_J_kgK", 188.9)),
            },
        },
        "shockwave": {
            "r_grid_m": [0, 1, 2, 3, 5] + list(range(10, 101, 5)) + [125, 150, 200, 300, 400],
            "explosion_mode": "deflagration",
            "range_id": int(pouo.inputs.get("range_id", 3) or 3),
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


def _build_lpg_pipe_jet_fire_inputs(
    pouo: POUOInput,
    cfg: EngineConfig,
    accumulated: dict,
) -> Dict[str, Any]:
    """POUO6 факельное горение: константы берём из templatePOUO6, раздел 11.3."""
    m_dot = float(accumulated.get("m_dot_kg_s", 0.0) or 0.0)
    if m_dot <= 0:
        raise ValueError("POUO6: jet_fire требует рассчитанный m_dot_kg_s > 0.")
    lpg_input = pouo.inputs.get("lpg", {}) or {}
    return {
        "m_dot_kg_s": m_dot,
        # Шаблон: жидкая фаза СУГ -> K=15; Ef = 80 кВт/м².
        "K": float(lpg_input.get("jet_K", 15.0)),
        "Ef_kw_m2": float(lpg_input.get("Ef_jet_kw_m2", 80.0)),
    }


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


def _build_lpg_pipe_fireball_inputs(
    pouo: POUOInput,
    cfg: EngineConfig,
    accumulated: dict,
) -> Dict[str, Any]:
    """POUO6 огненный шар: константы берём из templatePOUO6, раздел 11.2."""
    m_kg = float(accumulated.get("Mg_kg", 0.0) or 0.0)
    if m_kg <= 0:
        raise ValueError("POUO6: fireball требует рассчитанный Mg_kg > 0.")
    lpg_input = pouo.inputs.get("lpg", {}) or {}
    return {
        "m_kg": m_kg,
        # Шаблон: Ef = 80 кВт/м² (Таблица П3.4 [21]).
        "Ef_kw_m2": float(lpg_input.get("Ef_fireball_kw_m2", 80.0)),
    }


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


def lpg_outdoor_pipe_scenarios() -> List[ScenarioConfig]:
    """
    Рецепт POUO6: СУГ, наружный трубопровод/испарительная установка.

    Цепочка:
      выброс Mg -> flash/cloud в TVS branch -> shockwave,
      затем jet_fire по m_flash/t_shutoff и fireball по Mg.
    """
    return [
        ScenarioConfig(
            "tvs_explosion",
            _build_lpg_pipe_tvs_inputs,
            requires=frozenset(),
            provides=frozenset({"m_dot_kg_s", "m_dot_peak_kg_s", "Mg_kg"}),
        ),
        ScenarioConfig(
            "jet_fire",
            _build_lpg_pipe_jet_fire_inputs,
            requires=frozenset({"m_dot_kg_s"}),
            provides=frozenset(),
        ),
        ScenarioConfig(
            "fireball",
            _build_lpg_pipe_fireball_inputs,
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
            "rho_liq":               cfg.diesel_rho_liq_kg_m3,
            "eud0_j_per_kg":         cfg.diesel_eud0_j_per_kg,
            # Константы испарения (METHODOLOGY_POUO1_DT.md, Р.2)
            "Pnas_kpa":              cfg.diesel_Pnas_kpa,
            "M_g_mol":               cfg.diesel_M_g_mol,
            "T_calc_C":              cfg.diesel_calc_temp_c,
            "antoine_A":             cfg.diesel_antoine_A,
            "antoine_B":             cfg.diesel_antoine_B,
            "antoine_C":             cfg.diesel_antoine_C,
            "lower_flammability_pct": cfg.diesel_lower_flammability_pct,
            "formula_nC":            cfg.diesel_formula_nC,
            "formula_nH":            cfg.diesel_formula_nH,
            "formula_nX":            cfg.diesel_formula_nX,
            "formula_nO":            cfg.diesel_formula_nO,
            # Параметры пожара пролива
            "Ef_pool_kw_m2":         cfg.diesel_Ef_pool_kw_m2,
            "burn_rate_kg_m2_s":     cfg.diesel_burn_rate_kg_m2_s,
            # Параметры огненного шара.
            # ENGINEER_CHECK: 25 кВт/м² принято по DT-шаблону; ГОСТ-значение
            # 47 кВт/м² оставлено спорным местом в методологии.
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
            "range_id":      cfg.diesel_tvs_range_id if pouo.fuel_id == "diesel" else cfg.tvs_range_id,
            # Только diesel POUO1: методология принимает Vg=200 м/с как
            # верхнюю границу диапазона 4 для загромождённого пространства.
            "Vg_m_s":        cfg.diesel_tvs_vg_m_s if pouo.fuel_id == "diesel" else None,
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
      2. scenario_code == "POUO6"  → СУГ, наружные трубопроводы
      3. outdoor natgas            → трубопроводный газ
      4. всё остальное             → пустой список (заглушка)
    """
    fuel_norm = normalize_fuel_id(fuel_id)

    if scenario_code == "POUO1":
        return tank_park_scenarios()

    if scenario_code == "POUO6" and not is_indoor and fuel_norm == "lpg":
        return lpg_outdoor_pipe_scenarios()

    if not is_indoor and fuel_norm == "natgas":
        return natgas_outdoor_scenarios()

    # Заглушка: пустой список — runner вернёт пустой POUOResult
    return []
