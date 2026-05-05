# app/core/calcs/common/indoor_explosion_pressure.py
"""
Избыточное давление при дефлаграции горючего в замкнутом объёме (модель как в POUO3).

Не используется эквивалент TNT и не применяются уличные (открытая среда) модели ударной волны.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.pipeline.config import EngineConfig


def calc_indoor_explosion_pressure(
    m_total_kg: float,
    V_room_m3: float,
    *,
    c_st_percent: float,
    z: float,
    kn: float,
    rho_kg_m3: float,
    pmax_kpa: Optional[float] = None,
    p0_kpa: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Избыточное давление ΔP в помещении (замкнутый объём).

    Принято по методике шаблона POUO3 (см. ``indoor_natgas.explosion_indoor``).

    Обозначения:
      m_total — масса газа в расчётном сценарии M_g (кг), как правило суммарная
                масса участвующего топлива до взрыва;
      V_room  — свободный объём помещения V_free (м³);
      C_st    — стехиометрическая концентрация горючего в воздухе, % (объёмные доли × 100);
      Z       — коэффициент участия массы горючего во взрывоопасной смеси [0…1];
      K_n     — коэффициент заполнения помещения / непараллельности фронта (по методике);
      ρ       — плотность газовой фазы (кг/м³), согласованная с формулировкой методики;
      P_max, P_0 — давления для вспышки (кПа), по умолчанию из EngineConfig (POUO3).

    Формула:

      m_обл = m_total · Z

              /        m_обл        \\     / 100  \\   /  1  \\
      ΔP = (P_max - P_0) · | ------------ | · | ----- | · | --- |
              \\ V_room · ρ      /     \\ C_st /   \\ K_n /

    ΔP, P_max, P_0 — в кПа; m в кг; V в м³; ρ в кг/м³; C_st — в процентах.
    """
    cfg = EngineConfig()
    p_max = float(pmax_kpa if pmax_kpa is not None else cfg.indoor_natgas_Pmax_kPa)
    p0 = float(p0_kpa if p0_kpa is not None else cfg.indoor_natgas_P0_kPa)

    if V_room_m3 <= 0:
        raise ValueError("V_room_m3 должен быть > 0.")
    if rho_kg_m3 <= 0:
        raise ValueError("rho_kg_m3 должен быть > 0.")
    if kn <= 0 or c_st_percent <= 0:
        raise ValueError("kn и c_st_percent должны быть > 0.")
    if not 0.0 <= z <= 1.0:
        raise ValueError("z должен быть в диапазоне [0, 1].")
    if p_max <= p0:
        raise ValueError("pmax_kpa должен быть больше p0_kpa.")
    if m_total_kg < 0:
        raise ValueError("m_total_kg не может быть отрицательным.")

    m_cloud_kg = m_total_kg * z
    delta_p_kpa = (p_max - p0) * (m_cloud_kg / (V_room_m3 * rho_kg_m3)) * (100.0 / c_st_percent) / kn

    return {
        "delta_p_kpa": delta_p_kpa,
        "delta_p_pa": delta_p_kpa * 1000.0,
        "m_cloud_kg": m_cloud_kg,
        "m_total_kg": m_total_kg,
        "V_room_m3": V_room_m3,
        "c_st_percent": c_st_percent,
        "z": z,
        "kn": kn,
        "rho_kg_m3": rho_kg_m3,
        "pmax_kpa": p_max,
        "p0_kpa": p0,
    }
