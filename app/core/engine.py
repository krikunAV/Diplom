# app/core/engine.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any

from app.core.models import Project, POUO, PipeRow
from app.core.fuels import get_fuel

from app.core.calcs.jetfire import calc_jet_fire, Phase
from app.core.calcs.fireball import calc_fireball
from app.core.calcs.tvs_explosion import calc_tvs_explosion


# -------------------- конфиг движка --------------------

@dataclass
class EngineConfig:
    # окружающая среда
    p_down_kpa: float = 101.3
    t_air_K: float = 293.15

    # коэффициенты истечения
    Cd: float = 0.62

    # коэффициент участия массы во взрыве (если нужно)
    z_cloud: float = 0.5

    # строить ли графики (tvs_explosion / jet_fire / fireball)
    make_charts: bool = True


# -------------------- вспомогательные функции --------------------

def _infer_phase(fuel_id_norm: str) -> Phase:
    """
    Для расчёта струйного факела нужен тип истечения.
    Пока делаем простое правило:
    - natgas -> compressed_gas
    - lpg    -> lpg_vapor
    - diesel -> diesel_liquid
    """
    if fuel_id_norm == "natgas":
        return "compressed_gas"
    if fuel_id_norm == "lpg":
        return "lpg_vapor"
    return "diesel_liquid"


def _tvs_defaults(fuel_id_norm: str) -> Dict[str, float]:
    """
    Минимальные справочные параметры для ТВС-расчёта (7.1 по методике).
    Если пользователь не вводит Cg, range_id и т.п., используем эти значения.

    При желании позже вынесем в fuels.py.
    """
    if fuel_id_norm == "natgas":
        return {
            "c_st": 9.36,      # %
            "c_g": 5.0,        # % (если неизвестно, можно брать НКПР)
            "sigma": 7.0,      # газовая смесь
            "range_id": 3.0,   # дефлаграция 200-300 (часто в примерах)
            "fuel_class": 2.0, # условно
            "space_kind": 4.0, # слабозагромождённое
        }
    if fuel_id_norm == "lpg":
        return {
            "c_st": 3.97,      # % (пропан)
            "c_g": 2.1,        # % (НКПР порядка 2.1)
            "sigma": 7.0,
            "range_id": 3.0,
            "fuel_class": 2.0,
            "space_kind": 3.0, # резервуарный парк/средняя загромождённость
        }
    # дизель (гетерогенное облако) – блок ТВС можно пока отключать
    return {
        "c_st": 0.0,
        "c_g": 0.0,
        "sigma": 4.0,
        "range_id": 3.0,
        "fuel_class": 3.0,
        "space_kind": 3.0,
    }


def select_accident_pipe(p: POUO) -> Optional[PipeRow]:
    """Возвращает аварийный участок, если отмечен; иначе первый."""
    for pipe in p.pipes:
        if getattr(pipe, "is_accident", False):
            return pipe
    return p.pipes[0] if p.pipes else None


def _get_pressure_up_kpa(p: POUO, pipe: PipeRow) -> float:
    """
    Давление берём по правилу:
    - если у трубы задано pressure_kpa > 0 -> используем его
    - иначе -> inputs["P0_kpa"]
    """
    p_pipe = float(getattr(pipe, "pressure_kpa", 0.0) or 0.0)
    if p_pipe > 0:
        return p_pipe
    return float(p.inputs.get("P0_kpa", 0.0) or 0.0)


# -------------------- основной расчёт для одного сценария --------------------

def compute_for_pouo(p: POUO, cfg: EngineConfig | None = None) -> None:
    """
    Заполняет p.results структурой:
      results["release"]
      results["jet_fire"]
      results["fireball"]
      results["tvs_explosion"]

    Indoor: не считаем fireball/jet_fire/tvs_explosion.
    """
    cfg = cfg or EngineConfig()

    fuel = get_fuel(p.fuel_id)
    fuel_id = fuel.id

    # базовые входы
    t_shutoff_s = float(p.inputs.get("t_shutoff_s", 0.0) or 0.0)

    # всегда пишем “паспорт” сценария
    p.results.setdefault("meta", {})
    p.results["meta"].update({
        "fuel_id_norm": fuel_id,
        "fuel_title": fuel.title,
        "is_indoor": bool(p.is_indoor),
        "code": p.code,
        "title": p.title,
    })

    # --- indoor: только сохраняем то, что нужно для будущих indoor-расчётов ---
    if p.is_indoor:
        p.results["room"] = {
            "V_room_m3": float(p.inputs.get("V_room_m3", 0.0) or 0.0),
            "P0_kpa": float(p.inputs.get("P0_kpa", 0.0) or 0.0),
            "t_shutoff_s": t_shutoff_s,
        }
        return

    # --- outdoor: нужен аварийный участок ---
    acc = select_accident_pipe(p)
    if acc is None:
        p.results["error"] = "Нет труб для расчёта (p.pipes пуст)."
        return

    # если не отмечен аварийный — предупредим
    if not getattr(acc, "is_accident", False):
        p.results.setdefault("warnings", [])
        p.results["warnings"].append("Аварийный участок не отмечен — выбран первый участок списка.")

    P_up_kpa = _get_pressure_up_kpa(p, acc)
    d_hole_mm = float(acc.diameter_mm)  # толщины нет — используем диаметр как диаметр разрыва

    if P_up_kpa <= 0:
        p.results["error"] = "Не задано давление (inputs['P0_kpa'] или pipe.pressure_kpa)."
        return
    if d_hole_mm <= 0:
        p.results["error"] = "Некорректный диаметр аварийного участка."
        return

    phase = _infer_phase(fuel_id)

    # ---------- 1) RELEASE (G и масса выброса) ----------
    # G берём из jet_fire (он внутри считает расход)
    jf = calc_jet_fire(
        fuel_id=fuel_id,
        fuel_title=fuel.title,
        phase=phase,
        P_up_kpa=P_up_kpa,
        d_inner_mm=d_hole_mm,  # тут это диаметр отверстия/разрыва
        hole_mode="full_bore",
        P_down_kpa=cfg.p_down_kpa,
        T_K=cfg.t_air_K,
        Cd=cfg.Cd,
        Ef_kw_m2=80.0,  # как в примере/шаблоне; потом уточним по топливу
        chart_name=f"jetfire_{p.code}.png".replace(" ", "_"),
    )

    G = float(jf.G_kg_s)
    m_release = G * t_shutoff_s if t_shutoff_s > 0 else 0.0
    m_cloud = cfg.z_cloud * m_release

    p.results["release"] = {
        "accident_pipe": acc.name,
        "P_up_kpa": P_up_kpa,
        "d_hole_mm": d_hole_mm,
        "Cd": cfg.Cd,
        "T_air_K": cfg.t_air_K,
        "P_down_kpa": cfg.p_down_kpa,
        "G_kg_s": G,
        "t_shutoff_s": t_shutoff_s,
        "m_release_kg": m_release,
        "z_cloud": cfg.z_cloud,
        "m_cloud_kg": m_cloud,
    }

    # ---------- 2) JET FIRE ----------
    p.results["jet_fire"] = {
        "params": {
            "G_kg_s": jf.G_kg_s,
            "LF_m": jf.LF_m,
            "DF_m": jf.DF_m,
            "Ef_kw_m2": jf.Ef_kw_m2,
            "phase": jf.phase,
            "d_hole_mm": jf.d_hole_mm,
        },
        "table": jf.table_rows,
        "zones": jf.zones_rows,
        "chart_path": jf.chart_path,
    }

    # ---------- 3) FIREBALL (масса = выброс до отсечки) ----------
    if m_release > 0:
        fb = calc_fireball(
            fuel_id=fuel_id,
            fuel_title=fuel.title,
            m_kg=m_release,
            chart_name=f"fireball_{p.code}.png".replace(" ", "_"),
        )
        p.results["fireball"] = {
            "params": {
                "m_kg": fb.m_kg,
                "Ds_m": fb.Ds_m,
                "H_m": fb.H_m,
                "ts_s": fb.ts_s,
                "Ef_kw_m2": fb.Ef_kw_m2,
            },
            "table": fb.table_rows,
            "zones": fb.zones_rows,
            "chart_path": fb.chart_path,
        }
    else:
        p.results["fireball"] = {"skip_reason": "m_release_kg=0 (нет времени отсечки или G=0)"}

    # ---------- 4) TVS EXPLOSION (ударная волна) ----------
    # Делаем только для natgas/lpg (для дизеля пока пропускаем)
    if fuel_id not in {"natgas", "lpg"}:
        p.results["tvs_explosion"] = {"skip_reason": "Для данного топлива ТВС-взрыв не рассчитывается (пока)."}
        return

    # параметры ТВС: можно вводить в UI, иначе дефолты
    dflt = _tvs_defaults(fuel_id)

    c_g = float(p.inputs.get("C_g_vol_percent", dflt["c_g"]) or dflt["c_g"])
    c_st = float(p.inputs.get("C_st_vol_percent", dflt["c_st"]) or dflt["c_st"])
    sigma = float(p.inputs.get("sigma", dflt["sigma"]) or dflt["sigma"])
    range_id = int(float(p.inputs.get("range_id", dflt["range_id"]) or dflt["range_id"]))

    # теплота сгорания (берём из fuels.py)
    q_g = float(getattr(fuel, "eud0_j_per_kg", 0.0) or 0.0)
    if q_g <= 0:
        # запасной дефолт
        q_g = 5.0e7 if fuel_id == "natgas" else 4.6e7

    # масса в облаке, участвующая во взрыве
    if m_cloud <= 0:
        p.results["tvs_explosion"] = {"skip_reason": "m_cloud_kg=0 (нет времени отсечки или G=0)"}
        return

    tvs = calc_tvs_explosion(
        m_g_kg=m_cloud,
        q_g_j_per_kg=q_g,
        c_g=c_g,
        c_st=c_st,
        fuel_class=2,                 # можно позже сделать ввод
        space_kind="type4",           # можно позже сделать ввод
        range_id=range_id,            # 1..6
        sigma=sigma,
        max_r_m=float(p.inputs.get("tvs_r_max_m", 200.0) or 200.0),
        make_charts=cfg.make_charts,
        chart_dp_path=f"out/charts/tvs_dp_{p.code}.png".replace(" ", "_"),
        chart_imp_path=f"out/charts/tvs_imp_{p.code}.png".replace(" ", "_"),
    )

    p.results["tvs_explosion"] = {
        "params": tvs.params,
        "table": tvs.table_rows,
        "chart_dp_path": tvs.chart_dp_path,
        "chart_imp_path": tvs.chart_imp_path,
    }


# -------------------- расчёт проекта --------------------

def compute_project(project: Project, cfg: EngineConfig | None = None) -> None:
    cfg = cfg or EngineConfig()
    for p in project.pouos:
        compute_for_pouo(p, cfg)