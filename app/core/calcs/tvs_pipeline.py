# app/core/calcs/tvs_pipeline.py
from __future__ import annotations

from app.core.context import CalculationContext
from app.core.validate_context import validate_context_inputs

from app.core.calcs.tvs.release_cloud_energy import run_release_cloud_energy
from app.core.calcs.tvs.shockwave import run_shockwave
from app.core.calcs.tvs.probit_zones import run_probit_zones


def calc_tvs_pipeline(inputs: dict) -> CalculationContext:
    """
    Цепочка 7.1 (без мат.ущерба и жертв):
      Выброс -> Облако ТВС -> Энергия -> Ударная волна (412) -> Радиусы зон

    Возвращает CalculationContext (inputs/intermediate/results/logs).
    """
    errs = validate_context_inputs(inputs)
    if errs:
        msg = "Invalid inputs:\n" + "\n".join([f"- {e}" for e in errs])
        raise ValueError(msg)

    ctx = CalculationContext(inputs=inputs)
    ctx.set_scenario(inputs.get("meta", {}).get("scenario_id", "unknown"))

    run_release_cloud_energy(ctx)
    run_shockwave(ctx)
    run_probit_zones(ctx)

    return ctx