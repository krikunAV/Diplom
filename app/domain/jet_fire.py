# app/domain/jet_fire.py
from __future__ import annotations

from typing import Any, Dict

from app.core.context import CalculationContext
from app.core.calcs.fire.jet_fire import calc_jetfire_by_M
from app.domain.base import BaseScenario


def _run_jet_fire(ctx: CalculationContext) -> None:
    m_dot = float(ctx.inputs.get("m_dot_kg_s", 0.0))
    result = calc_jetfire_by_M(M_kg_s=m_dot)
    ctx.results.update(result)
    ctx.log(f"[jet_fire] m_dot={m_dot:.4f} kg/s")


class JetFireScenario(BaseScenario):
    """
    Сценарий: Факельное горение (jet fire).

    Формат raw_inputs:
      m_dot_kg_s: массовый расход горючего
    """

    scenario_type = "jet_fire"
    modules = [_run_jet_fire]

    def prepare(self, raw_inputs: Dict[str, Any]) -> CalculationContext:
        return CalculationContext(inputs=raw_inputs)
