# app/core/engine.py
#
# BACKWARD-COMPAT WRAPPER.
# Вся логика перенесена в:
#   app/pipeline/runner.py    — оркестрация
#   app/pipeline/config.py   — EngineConfig
#   app/domain/              — сценарии
#   app/core/calcs/          — математические модули
#
# Этот файл сохраняет публичный интерфейс (compute_for_pouo / compute_project)
# чтобы UI и run_report_demo.py продолжали работать без изменений.
#
from __future__ import annotations

import logging

from app.pipeline.config import EngineConfig  # re-export
from app.pipeline.runner import (
    run_pouo,
    run_project as _run_project,
    pouo_to_input,
    project_to_input,
)
from app.core.models import POUO, Project

logger = logging.getLogger(__name__)


def _pouo_result_to_legacy(p: POUO, pouo_result) -> None:
    """
    Переносит данные из нового POUOResult обратно в p.results
    в формате, который ожидает word_builder и UI.
    """
    p.results = {}

    # meta
    from app.core.fuels import get_fuel
    fuel = get_fuel(p.fuel_id)
    p.results["meta"] = {
        "fuel_id_norm": fuel.id,
        "fuel_title": fuel.title,
        "is_indoor": bool(p.is_indoor),
        "code": p.code,
        "title": p.title,
    }

    # indoor / error / skip
    if "indoor" in pouo_result.scenarios:
        sr = pouo_result.scenarios["indoor"]
        p.results["room"] = {
            "V_room_m3": float(p.inputs.get("V_room_m3", 0.0) or 0.0),
            "P0_kpa": float(p.inputs.get("P0_kpa", 0.0) or 0.0),
            "t_shutoff_s": float(p.inputs.get("t_shutoff_s", 0.0) or 0.0),
        }
        p.results["skip"] = sr.error or "Indoor-сценарий пока не подключён."
        return

    for key in ("error", "skip"):
        if key in pouo_result.scenarios:
            sr = pouo_result.scenarios[key]
            p.results[key] = sr.error
            return

    # ── POUO3: indoor natgas ─────────────────────────────────────────────────
    indoor_sr = pouo_result.scenarios.get("indoor_natgas")
    if indoor_sr:
        if indoor_sr.ok:
            ctx = indoor_sr.ctx
            inter = ctx.intermediate
            res = ctx.results
            rel_inputs = ctx.inputs.get("release", {}) if ctx.inputs else {}
            subst_inputs = ctx.inputs.get("substance", {}) if ctx.inputs else {}
            cloud_inputs = ctx.inputs.get("cloud", {}) if ctx.inputs else {}
            room_inputs = ctx.inputs.get("room", {}) if ctx.inputs else {}
            acc_pipe = next((pipe for pipe in p.pipes if getattr(pipe, "is_accident", False)), None)
            acc_pipe = acc_pipe or (p.pipes[0] if p.pipes else None)

            p.results["room"] = {
                "V_room_m3": float(p.inputs.get("V_room_m3", 0.0) or 0.0),
                "V_free_m3": room_inputs.get("V_free_m3"),
                "Pmax_kPa": room_inputs.get("Pmax_kPa"),
                "P0_kPa": room_inputs.get("P0_kPa"),
                "Kn": room_inputs.get("Kn"),
                "C_st_percent": room_inputs.get("C_st_percent"),
            }
            p.results["release"] = {
                "accident_pipe": (acc_pipe.name if acc_pipe else ""),
                "P_up_kpa": (
                    float(rel_inputs.get("Pg_Pa", 0.0) or 0.0) / 1000.0
                ),
                "P2_kpa": (ctx.inputs.get("isolated_section", {}) or {}).get("P2_kPa"),
                "d_hole_mm": float(acc_pipe.diameter_mm) if acc_pipe else 0.0,
                "d_m": rel_inputs.get("orifice_d_m"),
                "t_shutoff_s": rel_inputs.get("t_shutoff_s"),
                "T_K": rel_inputs.get("T_K"),
                "R0_J_kgK": rel_inputs.get("R0_J_kgK"),
                "rho_n_kg_m3": subst_inputs.get("rho_gas_kg_m3"),
                "Z": cloud_inputs.get("Z"),
                "F_m2": inter.get("F_m2"),
                "v_g_m3_kg": inter.get("v_g_m3_kg"),
                "m_dot_kg_s": inter.get("m_dot_kg_s"),
                "G_kg_s": inter.get("m_dot_kg_s"),
                "M1T_kg": inter.get("M1T_kg"),
                "V1T_m3": inter.get("V1T_m3"),
                "sum_r2L_m3": inter.get("sum_r2L_m3"),
                "V2T_m3": inter.get("V2T_m3"),
                "M2T_kg": inter.get("M2T_kg"),
                "Mg_kg": inter.get("Mg_kg"),
                "M_total_kg": inter.get("Mg_kg"),
                "cloud_mass_kg": inter.get("m_cloud_kg"),
                "m_cloud_kg": inter.get("m_cloud_kg"),
            }
            p.results["indoor_explosion"] = {
                "inputs": ctx.inputs,
                "intermediate": inter,
                "results": res,
                "logs": ctx.logs,
                "deltaP_kPa": res.get("deltaP_kPa"),
                "deltaP_Pa": res.get("deltaP_Pa"),
            }
        else:
            p.results["error"] = indoor_sr.error

    # ── POUO4: indoor LPG ────────────────────────────────────────────────────
    indoor_lpg_sr = pouo_result.scenarios.get("indoor_lpg")
    if indoor_lpg_sr:
        if indoor_lpg_sr.ok:
            ctx = indoor_lpg_sr.ctx
            inter = ctx.intermediate
            res = ctx.results
            rel_inputs = ctx.inputs.get("release", {}) if ctx.inputs else {}
            subst_inputs = ctx.inputs.get("substance", {}) if ctx.inputs else {}
            cloud_inputs = ctx.inputs.get("cloud", {}) if ctx.inputs else {}
            room_inputs = ctx.inputs.get("room", {}) if ctx.inputs else {}
            acc_pipe = next((pipe for pipe in p.pipes if getattr(pipe, "is_accident", False)), None)
            acc_pipe = acc_pipe or (p.pipes[0] if p.pipes else None)

            p.results["room"] = {
                "V_room_m3": float(p.inputs.get("V_room_m3", 0.0) or 0.0),
                "V_free_m3": room_inputs.get("V_free_m3"),
                "Pmax_kPa": room_inputs.get("Pmax_kPa"),
                "P0_kPa": room_inputs.get("P0_kPa"),
                "Kn": room_inputs.get("Kn"),
                "C_st_percent": room_inputs.get("C_st_percent"),
            }
            p.results["release"] = {
                "accident_pipe": (acc_pipe.name if acc_pipe else ""),
                "P_up_kpa": (
                    float(rel_inputs.get("Pg_Pa", 0.0) or 0.0) / 1000.0
                ),
                "P2_kpa": (ctx.inputs.get("isolated_section", {}) or {}).get("P2_kPa"),
                "d_hole_mm": float(acc_pipe.diameter_mm) if acc_pipe else 0.0,
                "d_m": rel_inputs.get("orifice_d_m"),
                "t_shutoff_s": rel_inputs.get("t_shutoff_s"),
                "T_K": rel_inputs.get("T_K"),
                "R0_J_kgK": rel_inputs.get("R0_J_kgK"),
                "rho_n_kg_m3": subst_inputs.get("rho_gas_kg_m3"),
                "rho_gas_kg_m3": subst_inputs.get("rho_gas_kg_m3"),
                "rho_pipe_kg_m3": subst_inputs.get("rho_pipe_kg_m3"),
                "molar_mass_kg_kmol": subst_inputs.get("molar_mass_kg_kmol"),
                "V0_m3_kmol": subst_inputs.get("V0_m3_kmol"),
                "tp_C": subst_inputs.get("tp_C"),
                "Z": cloud_inputs.get("Z"),
                "F_m2": inter.get("F_m2"),
                "v_g_m3_kg": inter.get("v_g_m3_kg"),
                "m_dot_kg_s": inter.get("m_dot_kg_s"),
                "G_kg_s": inter.get("m_dot_kg_s"),
                "M1T_kg": inter.get("M1T_kg"),
                "V1T_m3": inter.get("V1T_m3"),
                "sum_r2L_m3": inter.get("sum_r2L_m3"),
                "V2T_m3": inter.get("V2T_m3"),
                "M2T_kg": inter.get("M2T_kg"),
                "Mg_kg": inter.get("Mg_kg"),
                "M_total_kg": inter.get("Mg_kg"),
                "cloud_mass_kg": inter.get("m_cloud_kg"),
                "m_cloud_kg": inter.get("m_cloud_kg"),
            }
            p.results["indoor_explosion"] = {
                "inputs": ctx.inputs,
                "intermediate": inter,
                "results": res,
                "logs": ctx.logs,
                "deltaP_kPa": res.get("deltaP_kPa"),
                "deltaP_Pa": res.get("deltaP_Pa"),
            }
        else:
            p.results["error"] = indoor_lpg_sr.error

    # ── TVS ──────────────────────────────────────────────────────────────────
    tvs_sr = pouo_result.scenarios.get("tvs_explosion")
    if tvs_sr and tvs_sr.ok:
        ctx = tvs_sr.ctx
        inter = ctx.intermediate
        res = ctx.results

        _rel_inputs = ctx.inputs.get("release", {}) if ctx.inputs else {}
        _subst_inputs = ctx.inputs.get("substance", {}) if ctx.inputs else {}
        _cloud_inputs = ctx.inputs.get("cloud", {}) if ctx.inputs else {}
        _acc_pipe = next((pipe for pipe in p.pipes if getattr(pipe, "is_accident", False)), None)
        _acc_pipe = _acc_pipe or (p.pipes[0] if p.pipes else None)
        p.results["release"] = {
            "accident_pipe": (_acc_pipe.name if _acc_pipe else ""),
            "P_up_kpa": float(p.inputs.get("P0_kpa", 0.0)),
            "P_liquid_kpa": float(p.inputs.get("P_liquid_kpa", p.inputs.get("P0_kpa", 0.0)) or 0.0),
            "P_vapor_kpa": float(p.inputs.get("P_vapor_kpa", 0.0) or 0.0),
            "d_hole_mm": float(_acc_pipe.diameter_mm) if _acc_pipe else 0.0,
            "d_m": _rel_inputs.get("orifice_d_m"),
            "t_shutoff_s": float(p.inputs.get("t_shutoff_s", 0.0)),
            # газовые константы (нужны шаблону для отображения формул)
            "T_K":       _rel_inputs.get("T_K"),
            "R0_J_kgK":  _rel_inputs.get("R0_J_kgK"),
            "rho_n_kg_m3": _subst_inputs.get("rho_gas_kg_m3"),
            "Z":         _cloud_inputs.get("Z"),
            # intermediate
            "F_m2":                    inter.get("F_m2"),
            "v_g_m3_kg":               inter.get("v_g_m3_kg"),
            "m_dot_release_kg_s":       inter.get("m_dot_release_kg_s"),
            "m_dot_kg_s":              inter.get("m_dot_kg_s"),
            "m_dot_peak_kg_s":          inter.get("m_dot_peak_kg_s"),
            "M1T_kg":                  inter.get("M1T_kg"),
            "V1T_m3":                   inter.get("V1T_m3"),
            "sum_r2L_m3":              inter.get("sum_r2L_m3"),
            "V2T_m3":                  inter.get("V2T_m3"),
            "M2T_kg":                  inter.get("M2T_kg"),
            "Mg_kg":                   inter.get("Mg_kg"),
            "M_total_kg":              inter.get("Mg_kg"),
            "vapor_mass_kg":            inter.get("vapor_mass_kg"),
            "liquid_mass_kg":           inter.get("liquid_mass_kg"),
            "cloud_mass_kg":            inter.get("cloud_mass_kg", inter.get("m_cloud_kg")),
            "tvs_cloud_mass_kg":        inter.get("tvs_cloud_mass_kg", inter.get("m_cloud_kg")),
            "total_mass_kg":            inter.get("total_mass_kg", inter.get("Mg_kg")),
            "vapor_volume_m3":          inter.get("vapor_volume_m3"),
            "liquid_gas_volume_m3":     inter.get("liquid_gas_volume_m3"),
            "GV_kg_s":                  inter.get("GV_kg_s"),
            "GL_kg_s":                  inter.get("GL_kg_s"),
            "Mzh_kg":                   inter.get("Mzh_kg"),
            "VGVS_m3":                  inter.get("VGVS_m3"),
            "mi_kg":                    inter.get("mi_kg"),
            "Mg_total_kg":              inter.get("Mg_total_kg"),
            "mg_tvs_kg":                inter.get("mg_tvs_kg"),
            "E_template_J":             inter.get("E_template_J"),
            "m_flash_kg":               inter.get("m_flash_kg"),
            "m_pool_evap_kg":           inter.get("m_pool_evap_kg"),
            "m_evap_kg":                inter.get("m_evap_kg"),
            "m_cloud_kg":              inter.get("m_cloud_kg"),
            "Eud_J_kg":                inter.get("Eud_J_kg"),
            "E_concentration_correction": inter.get("E_concentration_correction"),
            "E_J":                     inter.get("E_J"),
            # wind zones (вычисляются модулем run_wind_zones в TVS pipeline)
            **res.get("wind_zones", {}),
            # legacy aliases
            "G_kg_s":                  inter.get("m_dot_kg_s"),
            "m_release_kg":            inter.get("M1T_kg"),
            "P2_kpa":                  float(p.inputs.get("P0_kpa", 0.0)),
        }

        shock_params = res.get("shockwave_params", {}) or {}
        p.results["tvs_explosion"] = {
            "inputs":       ctx.inputs,
            "intermediate": inter,
            "results":      res,
            "logs":         ctx.logs,
            # table теперь строится в probit_zones.py — единственное место
            "table":        res.get("tvs_table", []),
            "flame_speed_m_s": shock_params.get("Vg_m_s"),
        }
    elif tvs_sr:
        p.results["error"] = tvs_sr.error

    # ── Jet fire ─────────────────────────────────────────────────────────────
    jf_sr = pouo_result.scenarios.get("jet_fire")
    if jf_sr:
        if jf_sr.ok:
            p.results["jet_fire"] = dict(jf_sr.ctx.results)
        else:
            p.results["jet_fire"] = {"skip_reason": jf_sr.error}
    else:
        jf_stub_sr = pouo_result.scenarios.get("jet_fire_stub")
        if not jf_stub_sr:
            jf_stub_sr = pouo_result.scenarios.get("lpg_jet_fire_stub")
        if jf_stub_sr:
            if jf_stub_sr.ok:
                p.results["jet_fire"] = dict(jf_stub_sr.ctx.results)
            else:
                p.results["jet_fire"] = {"skip_reason": jf_stub_sr.error}

    # ── Fireball ─────────────────────────────────────────────────────────────
    fb_sr = pouo_result.scenarios.get("fireball")
    if fb_sr:
        if fb_sr.ok:
            p.results["fireball"] = dict(fb_sr.ctx.results)
        else:
            p.results["fireball"] = {"skip_reason": fb_sr.error}

    # ── Tank park (резервуарный парк) ─────────────────────────────────────────
    tp_sr = pouo_result.scenarios.get("tank_park")
    if tp_sr:
        if tp_sr.ok:
            ctx = tp_sr.ctx
            inter = ctx.intermediate
            res = ctx.results

            # Основной блок результатов
            p.results["tank_park"] = {
                "inputs":       ctx.inputs,
                "intermediate": inter,
                "results":      res,
                "logs":         ctx.logs,
            }

            # release-совместимый блок для Word builder и UI summary
            p.results["release"] = {
                "fuel_id":       ctx.inputs.get("fuel", {}).get("id", ""),
                "m_total_kg":    inter.get("m_total_kg"),
                "m_evap_kg":     inter.get("m_evap_kg"),
                "m_flash_kg":    inter.get("m_flash_kg"),
                "m_cloud_kg":    inter.get("m_cloud_kg"),
                "Mg_kg":         inter.get("Mg_kg"),
                "m_dot_kg_s":    inter.get("m_dot_kg_s"),
                "m_dot_peak_kg_s": inter.get("m_dot_peak_kg_s"),
                "E_J":           inter.get("E_J"),
            }

            # Перекладываем результаты во top-level для UI/Word
            if "fireball" in res:
                p.results["fireball"] = res["fireball"]
            if "jet_fire" in res:
                p.results["jet_fire"] = res["jet_fire"]
            if "pool_fire" in res:
                p.results["pool_fire"] = res["pool_fire"]

            # ТВС-взрыв (только diesel)
            if inter.get("E_J") and res.get("dP_Pa"):
                p.results["tvs_explosion"] = {
                    "intermediate": inter,
                    "results":      res,
                    "table":        res.get("tvs_table", []),
                }

        else:
            p.results["error"] = tp_sr.error


def compute_for_pouo(p: POUO, cfg: EngineConfig | None = None) -> None:
    """
    Публичный API (backward compat).
    Запускает расчёт и записывает результаты в p.results.
    """
    cfg = cfg or EngineConfig()
    pouo_input = pouo_to_input(p)
    pouo_result = run_pouo(pouo_input, cfg)
    _pouo_result_to_legacy(p, pouo_result)

    # графики — после заполнения p.results
    if cfg.make_charts and p.results.get("tvs_explosion"):
        try:
            from app.report.charts import write_pouo_charts
            write_pouo_charts(
                results=p.results,
                output_dir=cfg.charts_output_dir,
                pouo_code=p.code,
            )
        except Exception:
            logger.exception("Не удалось построить графики для %s; расчёт не прерывается.", p.code)


def compute_project(project: Project, cfg: EngineConfig | None = None) -> None:
    """Запускает расчёт для всех ПООУ проекта."""
    cfg = cfg or EngineConfig()
    for p in project.pouos:
        compute_for_pouo(p, cfg)
