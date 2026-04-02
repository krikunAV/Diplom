# app/domain/tvs_explosion.py
from __future__ import annotations

from typing import Any, Dict

from app.core.context import CalculationContext
from app.core.calcs.tvs.release_cloud_energy import run_release_cloud_energy
from app.core.calcs.tvs.shockwave import run_shockwave
from app.core.calcs.tvs.probit_zones import run_probit_zones
from app.domain.base import BaseScenario, ScenarioError


class TVSExplosionScenario(BaseScenario):
    """
    Сценарий: Взрыв топливо-воздушной смеси (ТВС).

    Pipeline модулей:
      1. release_cloud_energy  — масса выброса, облако, удельная энергия
      2. shockwave             — ΔP(r), I+(r) по сетке радиусов
      3. probit_zones          — зоны стекло/здания/люди + таблица пробит

    Формат raw_inputs:
      meta:             {scenario_id, notes}
      env:              {P0_Pa, C0_mps, wind_mps}
      substance:        {rho_gas_kg_m3, Eud0_J_kg, beta, sigma, C_st_kg_m3, C_g_kg_m3}
      release:          {orifice_d_m, mu, psi, Pg_Pa, T_K, R0_J_kgK, t_shutoff_s}
      isolated_section: {P2_kPa, pipes: [{r_m, L_m}]}
      cloud:            {Z, cloud_model}
      shockwave:        {r_grid_m, explosion_mode, range_id}
    """

    scenario_type = "tvs_explosion"
    modules = [run_release_cloud_energy, run_shockwave, run_probit_zones]

    def prepare(self, raw_inputs: Dict[str, Any]) -> CalculationContext:
        return CalculationContext(inputs=raw_inputs)

    def validate(self, ctx: CalculationContext) -> None:
        from app.core.validate_context import validate_context_inputs

        errors = validate_context_inputs(ctx.inputs)
        if errors:
            raise ScenarioError(
                "Ошибки входных данных TVS:\n" + "\n".join(f"  - {e}" for e in errors)
            )
