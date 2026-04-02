# app/domain/fireball.py
from __future__ import annotations

from typing import Any, Dict

from app.core.context import CalculationContext
from app.core.calcs.fire.fireball import calc_fireball_by_M
from app.domain.base import BaseScenario


def _run_fireball(ctx: CalculationContext) -> None:
    m_kg = float(ctx.inputs.get("m_kg", 0.0))
    result = calc_fireball_by_M(m_kg=m_kg)
    ctx.results.update(result)
    ctx.log(f"[fireball] m={m_kg:.2f} kg")


class FireballScenario(BaseScenario):
    """
    Сценарий: Огненный шар.

    Формат raw_inputs:
      m_kg: суммарная масса горючего в выбросе
    """

    scenario_type = "fireball"
    modules = [_run_fireball]

    def prepare(self, raw_inputs: Dict[str, Any]) -> CalculationContext:
        return CalculationContext(inputs=raw_inputs)
