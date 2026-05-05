from __future__ import annotations

from typing import Any, Dict

from app.core.context import CalculationContext
from app.core.calcs.indoor_lpg import (
    explosion_indoor,
    gas_release,
    jet_fire_stub,
    mass_calculation,
)
from app.domain.base import BaseScenario, ScenarioError


class IndoorLpgScenario(BaseScenario):
    """
    POUO4: внутренний трубопровод СУГ в помещении.

    Формат raw_inputs:
      meta:             {scenario_id, notes}
      release:          {orifice_d_m, mu, psi, Pg_Pa, T_K, R0_J_kgK, t_shutoff_s}
      isolated_section: {P2_kPa, pipes: [{r_m, L_m}]}
      substance:        {rho_gas_kg_m3, rho_pipe_kg_m3}
      cloud:            {Z}
      room:             {V_free_m3, Pmax_kPa, P0_kPa, Kn, C_st_percent}
    """

    scenario_type = "indoor_lpg"
    modules = [gas_release, mass_calculation, explosion_indoor]

    def prepare(self, raw_inputs: Dict[str, Any]) -> CalculationContext:
        return CalculationContext(inputs=raw_inputs)

    def validate(self, ctx: CalculationContext) -> None:
        required_groups = ("release", "isolated_section", "substance", "cloud", "room")
        missing = [name for name in required_groups if name not in ctx.inputs]
        if missing:
            raise ScenarioError("POUO4: отсутствуют группы входных данных: " + ", ".join(missing))


class LpgJetFireStubScenario(BaseScenario):
    """Заглушка для раздела 9.3 templatePOUO4.docx."""

    scenario_type = "lpg_jet_fire_stub"
    modules = [jet_fire_stub]

    def prepare(self, raw_inputs: Dict[str, Any]) -> CalculationContext:
        return CalculationContext(inputs=raw_inputs)
