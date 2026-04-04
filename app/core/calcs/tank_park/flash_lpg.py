# app/core/calcs/tank_park/flash_lpg.py
"""
Модуль 1 (lpg): мгновенное вскипание СУГ при разгерметизации резервуара.

Физическая модель:
  СУГ хранится при давлении; T_кип ≈ −42°C. При разгерметизации давление
  резко падает, и часть жидкости мгновенно испаряется (flash evaporation).

  flash_fraction ≈ Cp · ΔT / L_vap
    Cp    ≈ 2300 Дж/(кг·К)
    ΔT    = T_окр − T_кип ≈ 20 − (−42) = 62°C
    L_vap ≈ 370 000 Дж/кг
    → ≈ 0.386; принимаем консервативно 0.30

  Остаток жидкости образует пролив, из которого испаряется ещё часть.

Входные данные из ctx.inputs:
  spill.duration_s           — продолжительность выброса, с
  spill.flash_fraction       — доля мгновенного вскипания (default 0.30)
  spill.pool_evap_fraction   — доля испарения из пролива (default 0.10)

Читает из ctx.intermediate:
  m_total_kg

Записывает в ctx.intermediate:
  m_flash_kg      — масса мгновенно испарившегося СУГ, кг
  m_pool_evap_kg  — масса, испарившаяся из пролива, кг
  m_evap_kg       — суммарная масса газообразного СУГ, кг
  Mg_kg           — m_total (для BLEVE-огненного шара: весь резервуар)
  m_dot_kg_s      — эквивалентный расход для модели факела, кг/с
  m_dot_peak_kg_s — пиковый расход (m_flash / peak_duration_s), кг/с
"""
from __future__ import annotations

from app.core.context import CalculationContext


def run_lpg_flash(ctx: CalculationContext) -> None:
    """
    Мгновенное вскипание СУГ + эквивалентный массовый расход для факела.

    Струйный факел:
      m_dot = m_flash / duration_s  — средний расход испарённого СУГ [кг/с]

    Огненный шар (BLEVE):
      m_fireball = m_total          — весь объём резервуара (консервативно)
    """
    spill = ctx.inputs["spill"]

    duration_s = float(spill["duration_s"])
    flash_fraction = float(spill.get("flash_fraction", 0.30))
    pool_evap_fraction = float(spill.get("pool_evap_fraction", 0.10))
    peak_duration_s = float(spill.get("peak_duration_s", 2.5))

    m_total = float(ctx.intermediate["m_total_kg"])

    if duration_s <= 0:
        raise ValueError("spill.duration_s должна быть > 0")
    if not 0 < flash_fraction <= 1:
        raise ValueError("flash_fraction должна быть в (0, 1]")

    # ── Мгновенное вскипание ─────────────────────────────────────────────────
    m_flash = m_total * flash_fraction
    m_remaining = m_total - m_flash

    # ── Испарение из пролива остаточной жидкости ─────────────────────────────
    m_pool_evap = m_remaining * pool_evap_fraction
    m_evap = m_flash + m_pool_evap

    # ── Эквивалентный расход для модели факела ───────────────────────────────
    # Весь flash-объём — это и есть "струйный выброс" за время duration_s
    m_dot = m_flash / duration_s
    # Пиковый расход на коротком интервале (методика: 2–3 с после разгерметизации)
    m_dot_peak = (m_flash / peak_duration_s) if peak_duration_s > 0 else m_dot

    # ── Запись ───────────────────────────────────────────────────────────────
    ctx.intermediate["m_flash_kg"] = m_flash
    ctx.intermediate["m_pool_evap_kg"] = m_pool_evap
    ctx.intermediate["m_evap_kg"] = m_evap
    ctx.intermediate["Mg_kg"] = m_total          # для BLEVE-огненного шара
    ctx.intermediate["m_dot_kg_s"] = m_dot       # для струйного факела
    ctx.intermediate["m_dot_peak_kg_s"] = m_dot_peak

    ctx.log(
        f"[lpg_flash] m_total={m_total:.1f} кг, "
        f"flash={flash_fraction:.0%} → m_flash={m_flash:.1f} кг, "
        f"pool_evap={m_pool_evap:.1f} кг, "
        f"m_dot={m_dot:.2f} кг/с, m_dot_peak={m_dot_peak:.2f} кг/с"
    )
