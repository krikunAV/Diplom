# app/core/calcs/tank_park/evaporation_diesel.py
"""
Модуль 1 (diesel): испарение из пролива + формирование облака ТВС + энергозапас.

Нормативная основа:
  ГОСТ Р 12.3.047-2012, Приложение К — скорость испарения жидкостей
  РД 03-409-01, п.3 — коэффициент Z участия массы
  Ростехнадзор №412, п.7.1 — энергозапас облака

Входные данные из ctx.inputs:
  spill.area_m2       — площадь пролива, м²
  spill.duration_s    — расчётное время испарения, с
  spill.eta           — коэффициент ветровой нагрузки (default 1)
  fuel.Pnas_kpa       — давление насыщенного пара при расчётной температуре, кПа
  fuel.T_calc_C       — расчётная температура, °C
  fuel.antoine_*      — константы Антуана для уточнения Pnas
  fuel.M_g_mol        — молярная масса, г/моль
  fuel.eud0_j_per_kg  — удельная теплота сгорания, Дж/кг
  substance.beta      — коэффициент эффективности горения
  cloud.Z             — коэффициент участия массы в облаке (0.1)

Читает из ctx.intermediate:
  m_total_kg          — из run_tank_mass

Записывает в ctx.intermediate:
  W_evap_kg_m2_s      — скорость испарения, кг/(м²·с)
  rho_vapor_kg_m3     — плотность паров при расчётной температуре, кг/м³
  m_evap_kg           — масса испарившегося топлива, кг
  R_NKPR_m            — радиус зоны НКПР, м
  R_PVS_m             — радиус облака ПВС, м
  k_stoich            — стехиометрический коэффициент
  C_st_pct            — стехиометрическая концентрация, % об.
  m_cloud_kg          — масса горючего в облаке ТВС, кг
  Mg_kg               — то же (алиас, нужен для fireball через accumulated)
  Eud_J_kg            — удельная теплота сгорания с поправкой, Дж/кг
  E_J                 — энергозапас облака, Дж  ← нужен run_shockwave
"""
from __future__ import annotations

import math

from app.core.context import CalculationContext


def run_diesel_evaporation(ctx: CalculationContext) -> None:
    """
    Испарение дизельного топлива из пролива по METHODOLOGY_POUO1_DT.md:

        P_S = 10^(A - B/(C_A + t_P))          [кПа]
        rho_p = M / (V0 · (1 + 0.00367·t_P))  [кг/м³]
        W = 1·10⁻⁶ · η · P_S · √M             [кг/(м²·с)]
        R_NKPR = 3.2·(τ/3600)^0.5·(P_S/НКПР)^0.8·(m_i/(rho_p·P_S))^0.33

    где P_S  — давление насыщенного пара при расчётной температуре, **кПа**;
        M    — молярная масса, г/моль (= кг/кмоль);
        η    — коэффициент, зависящий от скорости ветра (1 при В ≤ 0.5 м/с).

    Масса испарившегося вещества:
        m_evap = W · F_пр · τ,   ограниченная m_total

    Облако ТВС и энергозапас:
        m_cloud = m_evap · Z
        Eud     = β · Eud0
        E       = m_cloud · Eud
    """
    spill = ctx.inputs["spill"]
    fuel = ctx.inputs["fuel"]
    subst = ctx.inputs["substance"]
    cloud = ctx.inputs["cloud"]

    area_m2 = float(spill["area_m2"])
    duration_s = float(spill["duration_s"])
    eta = float(spill.get("eta", 1.0))

    T_calc_C = float(fuel.get("T_calc_C", 36.0))
    Pnas_input_kpa = float(fuel["Pnas_kpa"])
    antoine_A = fuel.get("antoine_A")
    antoine_B = fuel.get("antoine_B")
    antoine_C = fuel.get("antoine_C")
    M_g_mol = float(fuel["M_g_mol"])
    eud0 = float(fuel["eud0_j_per_kg"])
    lower_flammability_pct = float(fuel.get("lower_flammability_pct", 0.6))
    nC = float(fuel.get("formula_nC", 12.343))
    nH = float(fuel.get("formula_nH", 26.889))
    nX = float(fuel.get("formula_nX", 0.0))
    nO = float(fuel.get("formula_nO", 0.0))
    beta = float(subst.get("beta", 1.0))
    Z = float(cloud["Z"])

    m_total = float(ctx.intermediate["m_total_kg"])

    if area_m2 <= 0:
        raise ValueError("spill.area_m2 должна быть > 0")
    if duration_s <= 0:
        raise ValueError("spill.duration_s должна быть > 0")
    if Pnas_input_kpa <= 0 or M_g_mol <= 0:
        raise ValueError("fuel.Pnas_kpa и fuel.M_g_mol должны быть > 0")
    if lower_flammability_pct <= 0:
        raise ValueError("fuel.lower_flammability_pct должен быть > 0")

    # ── Давление насыщенных паров (уравнение Антуана, Р.2.1) ─────────────────
    if antoine_A is not None and antoine_B is not None and antoine_C is not None:
        Pnas_kpa = 10.0 ** (
            float(antoine_A) - float(antoine_B) / (float(antoine_C) + T_calc_C)
        )
    else:
        Pnas_kpa = Pnas_input_kpa

    # ── Плотность паров (Р.2.2) ──────────────────────────────────────────────
    # ENGINEER_CHECK: в текстовой формуле шаблона знак скобок неоднозначен, но
    # численный пример ρп=6.79 получается именно при делении на температурную
    # поправку: M / (V0 · (1 + 0.00367·tP)).
    V0_m3_kmol = 22.4
    rho_vapor = M_g_mol / (V0_m3_kmol * (1.0 + 0.00367 * T_calc_C))

    # ── Скорость испарения (ГОСТ К.1, Pнас в кПа) ────────────────────────────
    W = 1e-6 * eta * Pnas_kpa * math.sqrt(M_g_mol)   # кг/(м²·с)

    # ── Масса испарившегося вещества ─────────────────────────────────────────
    m_evap_raw = W * area_m2 * duration_s
    m_evap = min(m_evap_raw, m_total)

    # ── Облако ТВС ────────────────────────────────────────────────────────────
    m_cloud = m_evap * Z

    # ── Радиусы НКПР/ПВС (Р.2.6-Р.2.7) ───────────────────────────────────────
    R_NKPR = 3.2 * ((duration_s / 3600.0) ** 0.5) * (
        (Pnas_kpa / lower_flammability_pct) ** 0.8
    ) * ((m_evap / (rho_vapor * Pnas_kpa)) ** 0.33)
    R_PVS = 1.2 * R_NKPR

    # ── Стехиометрия (Р.2.8-Р.2.9) ───────────────────────────────────────────
    k_stoich = nC + (nH - nX) / 4.0 - nO / 2.0
    C_st_pct = 100.0 / (1.0 + 4.84 * k_stoich)
    # По методологии концентрация облака принимается стехиометрической.
    C_g_pct = C_st_pct

    # ── Энергозапас (Ростехнадзор №412, п.7.1) ───────────────────────────────
    Eud = beta * eud0
    concentration_correction = 1.0 if C_g_pct <= C_st_pct else C_st_pct / C_g_pct
    E = m_cloud * Eud * concentration_correction

    # ── Запись в контекст ─────────────────────────────────────────────────────
    ctx.intermediate["Pnas_kpa"] = Pnas_kpa  # для отображения
    ctx.intermediate["T_calc_C"] = T_calc_C
    ctx.intermediate["rho_vapor_kg_m3"] = rho_vapor
    ctx.intermediate["W_evap_kg_m2_s"] = W
    ctx.intermediate["m_evap_raw_kg"] = m_evap_raw
    ctx.intermediate["m_evap_kg"] = m_evap
    ctx.intermediate["R_NKPR_m"] = R_NKPR
    ctx.intermediate["R_PVS_m"] = R_PVS
    ctx.intermediate["k_stoich"] = k_stoich
    ctx.intermediate["C_st_pct"] = C_st_pct
    ctx.intermediate["C_g_pct"] = C_g_pct
    ctx.intermediate["m_cloud_kg"] = m_cloud
    ctx.intermediate["Mg_kg"] = m_evap        # для огненного шара и accumulated
    ctx.intermediate["Eud_J_kg"] = Eud
    ctx.intermediate["E_concentration_correction"] = concentration_correction
    ctx.intermediate["E_J"] = E              # читает run_shockwave

    ctx.log(
        f"[diesel_evap] PS={Pnas_kpa:.3f} кПа, rho_p={rho_vapor:.3f} кг/м³, "
        f"W={W:.3e} кг/(м²·с), "
        f"m_evap={m_evap:.1f} кг (raw={m_evap_raw:.1f}), "
        f"R_NKPR={R_NKPR:.2f} м, R_PVS={R_PVS:.2f} м, "
        f"m_cloud={m_cloud:.2f} кг, E={E:.3e} Дж"
    )
