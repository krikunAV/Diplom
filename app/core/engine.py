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

from app.pipeline.config import EngineConfig  # re-export
from app.pipeline.runner import (
    run_pouo,
    run_project as _run_project,
    pouo_to_input,
    project_to_input,
)
from app.core.models import POUO, Project


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

    # ── TVS ──────────────────────────────────────────────────────────────────
    tvs_sr = pouo_result.scenarios.get("tvs_explosion")
    if tvs_sr and tvs_sr.ok:
        ctx = tvs_sr.ctx
        inter = ctx.intermediate
        res = ctx.results

        p.results["release"] = {
            "accident_pipe": (p.pipes[0].name if p.pipes else ""),
            "P_up_kpa": float(p.inputs.get("P0_kpa", 0.0)),
            "d_hole_mm": float(p.pipes[0].diameter_mm) if p.pipes else 0.0,
            "t_shutoff_s": float(p.inputs.get("t_shutoff_s", 0.0)),
            # intermediate
            "F_m2":                    inter.get("F_m2"),
            "v_g_m3_kg":               inter.get("v_g_m3_kg"),
            "m_dot_kg_s":              inter.get("m_dot_kg_s"),
            "M1T_kg":                  inter.get("M1T_kg"),
            "sum_r2L_m3":              inter.get("sum_r2L_m3"),
            "V2T_m3":                  inter.get("V2T_m3"),
            "M2T_kg":                  inter.get("M2T_kg"),
            "Mg_kg":                   inter.get("Mg_kg"),
            "M_total_kg":              inter.get("Mg_kg"),
            "m_cloud_kg":              inter.get("m_cloud_kg"),
            "Eud_J_kg":                inter.get("Eud_J_kg"),
            "E_concentration_correction": inter.get("E_concentration_correction"),
            "E_J":                     inter.get("E_J"),
            # wind zones (добавляются runner'ом прямо в ctx.results)
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

    # ── Fireball ─────────────────────────────────────────────────────────────
    fb_sr = pouo_result.scenarios.get("fireball")
    if fb_sr:
        if fb_sr.ok:
            p.results["fireball"] = dict(fb_sr.ctx.results)
        else:
            p.results["fireball"] = {"skip_reason": fb_sr.error}


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
            pass


def compute_project(project: Project, cfg: EngineConfig | None = None) -> None:
    """Запускает расчёт для всех ПООУ проекта."""
    cfg = cfg or EngineConfig()
    for p in project.pouos:
        compute_for_pouo(p, cfg)
