# app/core/calcs/tank_park/tank_mass.py
"""
Модуль 0 (общий): суммарная масса жидкого топлива в резервуарном парке.

Входные данные из ctx.inputs:
  tank.volume_m3  — объём одного резервуара, м³
  tank.count      — количество резервуаров
  fuel.rho_liq    — плотность жидкой фазы, кг/м³

Записывает в ctx.intermediate:
  m_total_kg      — суммарная масса жидкости
"""
from __future__ import annotations

from app.core.context import CalculationContext


def run_tank_mass(ctx: CalculationContext) -> None:
    """
    Суммарная масса жидкого горючего в резервуарном парке.

        m_total = V_tank × N_tank × ρ_liq

    Общий первый шаг для diesel и lpg.
    """
    tank = ctx.inputs["tank"]
    fuel = ctx.inputs["fuel"]

    volume_m3 = float(tank["volume_m3"])
    count = int(tank["count"])
    rho_liq = float(fuel["rho_liq"])

    if volume_m3 <= 0:
        raise ValueError("tank.volume_m3 должен быть > 0")
    if count < 1:
        raise ValueError("tank.count должен быть >= 1")
    if rho_liq <= 0:
        raise ValueError("fuel.rho_liq должен быть > 0")

    m_total = volume_m3 * count * rho_liq

    ctx.intermediate["volume_m3"] = volume_m3
    ctx.intermediate["count"] = count
    ctx.intermediate["rho_liq_kg_m3"] = rho_liq
    ctx.intermediate["m_total_kg"] = m_total
    ctx.log(
        f"[tank_mass] V={volume_m3} м³ × {count} рез. × ρ={rho_liq} кг/м³ "
        f"= m_total={m_total:.1f} кг"
    )
