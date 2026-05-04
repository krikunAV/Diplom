# app/domain/fireball.py
from __future__ import annotations

from typing import Any, Dict

from app.core.context import CalculationContext
from app.core.calcs.fire.fireball import calc_fireball_by_M
from app.domain.base import BaseScenario


def _run_fireball(ctx: CalculationContext) -> None:
    m_kg = float(ctx.inputs.get("m_kg", 0.0))
    Ef = float(ctx.inputs.get("Ef_kw_m2", 80.0))
    result = calc_fireball_by_M(m_kg=m_kg, Ef_kw_m2=Ef)
    ctx.results.update(result)
    ctx.log(f"[fireball] m={m_kg:.2f} kg, Ef={Ef:.3g} kW/m2")


class FireballScenario(BaseScenario):
    """
    Сценарий: Огненный шар.

    Формат raw_inputs:
      m_kg: суммарная масса горючего в выбросе
      Ef_kw_m2: optional surface emissive power
    """

    scenario_type = "fireball"
    modules = [_run_fireball]

    def prepare(self, raw_inputs: Dict[str, Any]) -> CalculationContext:
        return CalculationContext(inputs=raw_inputs)
