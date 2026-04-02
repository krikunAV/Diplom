# app/core/engine.py
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional, Dict, Any

from app.core.models import Project, POUO, PipeRow
from app.core.fuels import get_fuel
from app.core.calcs.tvs_pipeline import calc_tvs_pipeline
from app.core.calcs.fire.jet_fire import calc_jetfire_by_M
from app.core.calcs.fire.fireball import calc_fireball_by_M
from app.core.calcs.common.wind import calc_wind_zone
from app.core.calcs.common.probit import probit_to_percent, calc_people_probit, calc_building_probit
from app.report.charts import write_pouo_charts


@dataclass
class EngineConfig:
    # ---------------- Атмосфера / константы ----------------
    p0_pa: float = 101325.0
    c0_m_s: float = 330.0

    # ---------------- Методика расхода ----------------
    psi_critical: float = 0.7
    mu_orifice: float = 0.8
    T_gas_K: float = 293.0
    R0_natgas: float = 486.0       # Дж/(кг·К) — как в отчёте
    rho_natgas_n: float = 0.7      # кг/м3 — как в отчёте

    # ---------------- Коэффициент участия массы в облаке ----------------
    Z_cloud: float = 0.5

    # ---------------- ТВС ----------------
    tvs_range_id: int = 5
    tvs_sigma: float = 7.0
    tvs_max_r_m: float = 200.0

    # ---------------- Энергетика ----------------
    beta_natgas: float = 1.14
    eud0_base_j_per_kg: float = 44e6

    # ---------------- Прочее ----------------
    fuel_class_default: int = 4
    space_kind_default: str = "type3"
    make_charts: bool = True
    charts_output_dir: str = "out/charts"


def select_accident_pipe(p: POUO) -> Optional[PipeRow]:
    """
    Выбираем аварийный участок трубопровода:
    1) если явно помечен is_accident=True — берём его;
    2) иначе берём первый из списка.
    """
    for pipe in (p.pipes or []):
        if getattr(pipe, "is_accident", False):
            return pipe
    return p.pipes[0] if p.pipes else None


def _get_pressure_up_kpa(p: POUO, pipe: PipeRow) -> float:
    """
    Определяем рабочее давление:
    - если оно задано у трубы — используем его;
    - иначе берём из p.inputs["P0_kpa"].
    """
    p_pipe = float(getattr(pipe, "pressure_kpa", 0.0) or 0.0)
    if p_pipe > 0:
        return p_pipe
    return float(p.inputs.get("P0_kpa", 0.0) or 0.0)


def _cst_from_k(k: float) -> float:
    """
    Стехиометрическая концентрация:
        Cст = 100 / (1 + 4.84 * k)
    """
    return 100.0 / (1.0 + 4.84 * k)


def _choose_vg(range_id: int, m_cloud_kg: float) -> float | None:
    """
    Скорость фронта пламени для диапазона режима сгорания.

    Для твоего шаблона нужен диапазон 5:
        Vг = 43 * M^(1/6)

    Иногда может понадобиться диапазон 6:
        Vг = 26 * M^(1/6)
    """
    if m_cloud_kg <= 0:
        return None

    if range_id == 5:
        k1 = 43.0
    elif range_id == 6:
        k1 = 26.0
    else:
        # запасной вариант — используем тот же диапазон 5
        k1 = 43.0

    return k1 * (m_cloud_kg ** (1.0 / 6.0))


def _build_tvs_inputs_for_natgas(
    *,
    p: POUO,
    acc: PipeRow,
    P_up_kpa: float,
    t_shutoff_s: float,
    cfg: EngineConfig,
) -> Dict[str, Any]:
    """
    Подготовка входных данных для нового pipeline ТВС
    именно для природного газа (natgas).
    """
    d_m = float(acc.diameter_mm) / 1000.0

    # Собираем все трубы из изолированного участка
    pipes_data = []
    for pr in p.pipes:
        d_pipe_m = float(pr.diameter_mm) / 1000.0
        pipes_data.append({
            "r_m": d_pipe_m / 2.0,
            "L_m": float(pr.length_m),
        })

    P_r_pa = float(P_up_kpa) * 1000.0

    # Пока оставляем фиксированное значение как в твоём отчёте по метану
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
    Преобразует результаты pipeline в табличный вид для Word/UI.

    На выходе каждая строка содержит:
    - r_m
    - Rx
    - Px
    - Ix
    - deltaP_Pa
    - deltaP_kPa
    - Iplus_Pa_s

    И дополнительно:
    - Pr_people / prob_people
    - Pr_full / prob_full
    - Pr_heavy / prob_heavy

    Эти дополнительные поля нужны шаблону отчёта.
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
        delta_p_pa = float(dP[i])
        delta_p_kpa = delta_p_pa / 1000.0
        i_plus_pa_s = float(Iplus[i])

        pr_people = calc_people_probit(delta_p_pa, i_plus_pa_s)
        pr_full = calc_building_probit(delta_p_kpa, center_kpa=40.0, slope_kpa=5.0)
        pr_heavy = calc_building_probit(delta_p_kpa, center_kpa=30.0, slope_kpa=5.0)

        rows.append({
            "r_m": float(r_grid[i]),
            "Rx": float(Rx[i]),
            "Px": float(Px[i]),
            "Ix": float(Ix[i]),
            "deltaP_Pa": delta_p_pa,
            "deltaP_kPa": delta_p_kpa,
            "Iplus_Pa_s": i_plus_pa_s,

            "Pr_people": pr_people,
            "prob_people": probit_to_percent(pr_people),

            "Pr_full": pr_full,
            "prob_full": probit_to_percent(pr_full),

            "Pr_heavy": pr_heavy,
            "prob_heavy": probit_to_percent(pr_heavy),
        })

    return rows


def compute_for_pouo(p: POUO, cfg: EngineConfig | None = None) -> None:
    """
    Главная функция расчёта для одного ПООУ.

    Здесь:
    1. Проверяем входные данные;
    2. Выбираем аварийную трубу;
    3. Запускаем pipeline расчёта для natgas;
    4. Собираем результаты в p.results в формате, удобном для:
       - UI
       - Word-шаблона
       - графиков
    """
    cfg = cfg or EngineConfig()

    # Всегда пересчитываем результаты заново
    p.results = {}

    fuel = get_fuel(p.fuel_id)
    fuel_id = fuel.id

    # Общая мета-информация для интерфейса/отчёта
    p.results["meta"] = {
        "fuel_id_norm": fuel_id,
        "fuel_title": fuel.title,
        "is_indoor": bool(p.is_indoor),
        "code": p.code,
        "title": p.title,
    }

    # Indoor-сценарий пока не подключён к новому pipeline
    if p.is_indoor:
        p.results["room"] = {
            "V_room_m3": float(p.inputs.get("V_room_m3", 0.0) or 0.0),
            "P0_kpa": float(p.inputs.get("P0_kpa", 0.0) or 0.0),
            "t_shutoff_s": float(p.inputs.get("t_shutoff_s", 0.0) or 0.0),
        }
        p.results["skip"] = "Расчёт indoor-сценария пока не подключён к новому pipeline."
        return

    # Без труб считать нечего
    if not p.pipes:
        p.results["skip"] = "Нет труб для расчёта (сценарий без трубопроводов или не заполнено)."
        return

    # Выбираем аварийную трубу
    acc = select_accident_pipe(p)
    if acc is None:
        p.results["error"] = "Нет труб для расчёта."
        return

    # Давление и время отключения — обязательные параметры
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
            # 1. Готовим входные данные для нового pipeline
            inputs = _build_tvs_inputs_for_natgas(
                p=p,
                acc=acc,
                P_up_kpa=P_up_kpa,
                t_shutoff_s=t_shutoff_s,
                cfg=cfg,
            )

            # 2. Запускаем расчёт
            ctx = calc_tvs_pipeline(inputs)

            # 3. Забираем часто используемые промежуточные величины
            m_dot = float(ctx.intermediate.get("m_dot_kg_s", 0.0) or 0.0)
            mg = float(ctx.intermediate.get("Mg_kg", 0.0) or 0.0)

            # 4. Формируем release-блок для шаблона Word и UI
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
                "M_total_kg": mg,
                "m_cloud_kg": ctx.intermediate.get("m_cloud_kg"),
                "Eud_J_kg": ctx.intermediate.get("Eud_J_kg"),
                "E_concentration_correction": ctx.intermediate.get("E_concentration_correction"),
                "E_J": ctx.intermediate.get("E_J"),

                # Поля, которых ждёт шаблон
                "L_wind1_m": calc_wind_zone(m_dot, 1.0, 25.0),
                "L_wind3_m": calc_wind_zone(m_dot, 3.0, 25.0),
                "r0_wind1_m": calc_wind_zone(m_dot, 1.0, 12.5),
                "r0_wind3_m": calc_wind_zone(m_dot, 3.0, 12.5),

                # Совместимость со старым UI
                "G_kg_s": ctx.intermediate.get("m_dot_kg_s"),
                "m_release_kg": ctx.intermediate.get("M1T_kg"),
                "P2_kpa": float(P_up_kpa),
                "d_m": float(d_m),
                "R0_J_kgK": float(cfg.R0_natgas),
                "T_K": float(cfg.T_gas_K),
                "rho_n_kg_m3": float(cfg.rho_natgas_n),
                "Z": float(cfg.Z_cloud),
            }

            # 5. Формируем таблицу ТВС для отчёта
            tvs_table = _build_tvs_table_from_ctx(ctx)

            # 6. Берём параметры ударной волны,
            #    которые сохраняются в shockwave.py
            shock_params = ctx.results.get("shockwave_params", {}) or {}
            flame_speed = shock_params.get("Vg_m_s")

            # 7. Пробит для разрыва барабанных перепонок в точке r = 0
            pr4_r0 = None
            if tvs_table:
                dp0 = float(tvs_table[0].get("deltaP_Pa", 0.0) or 0.0)
                if dp0 > 0:
                    pr4_r0 = -12.6 + 1.524 * math.log(dp0)

            # 8. Итоговый блок ТВС
            p.results["tvs_explosion"] = {
                "inputs": ctx.inputs,
                "intermediate": ctx.intermediate,
                "results": ctx.results,
                "logs": ctx.logs,
                "table": tvs_table,
                "flame_speed_m_s": flame_speed,
                "pr4_r0": pr4_r0,
            }

            # 9. Отдельно считаем факельное горение
            p.results["jet_fire"] = calc_jetfire_by_M(M_kg_s=m_dot)

            # 10. Огненный шар — рассчитываем по суммарной массе выброса Mг
            p.results["fireball"] = calc_fireball_by_M(m_kg=mg)

            # 11. Графики — после всех расчётных блоков, если разрешено
            if cfg.make_charts:
                write_pouo_charts(
                    results=p.results,
                    output_dir=cfg.charts_output_dir,
                    pouo_code=p.code,
                )

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
    """
    Последовательно запускает расчёт для всех ПООУ проекта.
    """
    cfg = cfg or EngineConfig()
    for p in project.pouos:
        compute_for_pouo(p, cfg)