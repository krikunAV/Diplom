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
  fuel.Pnas_pa        — давление насыщенного пара при 20°C, Па
  fuel.M_g_mol        — молярная масса, г/моль
  fuel.eud0_j_per_kg  — удельная теплота сгорания, Дж/кг
  substance.beta      — коэффициент эффективности горения
  cloud.Z             — коэффициент участия массы в облаке (0.1)

Читает из ctx.intermediate:
  m_total_kg          — из run_tank_mass

Записывает в ctx.intermediate:
  W_evap_kg_m2_s      — скорость испарения, кг/(м²·с)
  m_evap_kg           — масса испарившегося топлива, кг
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
    Испарение дизельного топлива из пролива по ГОСТ Р 12.3.047-2012, Прил.К:

        W = 1·10⁻⁶ · η · Pнас · √M            [кг/(м²·с)]

    где Pнас — давление насыщенного пара при температуре воздуха, Па;
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

    Pnas_pa = float(fuel["Pnas_pa"])
    M_g_mol = float(fuel["M_g_mol"])
    eud0 = float(fuel["eud0_j_per_kg"])
    beta = float(subst.get("beta", 1.0))
    Z = float(cloud["Z"])

    m_total = float(ctx.intermediate["m_total_kg"])

    if area_m2 <= 0:
        raise ValueError("spill.area_m2 должна быть > 0")
    if duration_s <= 0:
        raise ValueError("spill.duration_s должна быть > 0")
    if Pnas_pa <= 0 or M_g_mol <= 0:
        raise ValueError("fuel.Pnas_pa и fuel.M_g_mol должны быть > 0")

    # ── Скорость испарения (ГОСТ К.1) ────────────────────────────────────────
    W = 1e-6 * eta * Pnas_pa * math.sqrt(M_g_mol)   # кг/(м²·с)

    # ── Масса испарившегося вещества ─────────────────────────────────────────
    m_evap_raw = W * area_m2 * duration_s
    m_evap = min(m_evap_raw, m_total)

    # ── Облако ТВС ────────────────────────────────────────────────────────────
    m_cloud = m_evap * Z

    # ── Энергозапас (Ростехнадзор №412, п.7.1) ───────────────────────────────
    Eud = beta * eud0
    E = m_cloud * Eud

    # ── Запись в контекст ─────────────────────────────────────────────────────
    ctx.intermediate["W_evap_kg_m2_s"] = W
    ctx.intermediate["m_evap_kg"] = m_evap
    ctx.intermediate["m_cloud_kg"] = m_cloud
    ctx.intermediate["Mg_kg"] = m_evap        # для огненного шара и accumulated
    ctx.intermediate["Eud_J_kg"] = Eud
    ctx.intermediate["E_J"] = E              # читает run_shockwave

    ctx.log(
        f"[diesel_evap] W={W:.3e} кг/(м²·с), "
        f"m_evap={m_evap:.1f} кг (raw={m_evap_raw:.1f}), "
        f"m_cloud={m_cloud:.2f} кг, E={E:.3e} Дж"
    )
