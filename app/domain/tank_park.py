# app/domain/tank_park.py
"""
Сценарий: Резервуарный парк (tank_park).

Поддерживает два вида топлива с разными физическими моделями:

    diesel → пролив → испарение → ТВС + огненный шар + пожар пролива
    lpg    → вскипание → струйный факел + огненный шар (BLEVE)

Ветвление по pipeline происходит в run() — выбирается список модулей
по значению raw_inputs["fuel"]["id"]. Это позволяет:
  - сохранить единый scenario_type = "tank_park"
  - использовать разные физические модели
  - переиспользовать run_shockwave / run_probit_zones / fireball / jet_fire
    без дублирования кода
"""
from __future__ import annotations

from typing import Any, Dict

from app.core.context import CalculationContext
from app.domain.base import BaseScenario

# ── Общие модули (оба топлива) ────────────────────────────────────────────────
from app.core.calcs.tank_park.tank_mass import run_tank_mass

# ── Diesel-специфичные модули ─────────────────────────────────────────────────
from app.core.calcs.tank_park.evaporation_diesel import run_diesel_evaporation
from app.core.calcs.tvs.shockwave import run_shockwave
from app.core.calcs.tvs.probit_zones import run_probit_zones
from app.core.calcs.tank_park.pool_fire import run_pool_fire

# ── LPG-специфичные модули ────────────────────────────────────────────────────
from app.core.calcs.tank_park.flash_lpg import run_lpg_flash

# ── Оценка числа людей в зонах поражения ─────────────────────────────────────
from app.core.calcs.tank_park.people_exposure import run_people_exposure

# ── Математические функции для огненного шара и факела ───────────────────────
from app.core.calcs.fire.fireball import calc_fireball_by_M
from app.core.calcs.fire.jet_fire import calc_jetfire_by_M


# ── Wrapper-модули (тонкий слой контекст ↔ чистые функции) ───────────────────

def _run_fireball_from_cloud(ctx: CalculationContext) -> None:
    """
    Огненный шар из паровоздушного облака (diesel).
    Масса = масса испарившегося топлива (m_evap_kg), как в
    METHODOLOGY_POUO1_DT.md. ENGINEER_CHECK: консервативный вариант с
    m_total_kg отмечен в методологии как требующий проверки.
    Ef берётся из fuel.Ef_fireball_kw_m2 (для DT-шаблона принято 25 кВт/м²).
    """
    m_kg = float(ctx.intermediate.get("m_evap_kg", 0.0))
    Ef = float(ctx.inputs["fuel"].get("Ef_fireball_kw_m2", 25.0))
    result = calc_fireball_by_M(m_kg=m_kg, Ef_kw_m2=Ef)
    ctx.results["fireball"] = result
    ctx.log(f"[fireball_cloud] m={m_kg:.2f} кг, Ef={Ef} кВт/м²")


def _run_fireball_bleve(ctx: CalculationContext) -> None:
    """
    Огненный шар BLEVE (lpg).
    Масса = суммарная масса жидкости в резервуарном парке (m_total_kg).
    Консервативный сценарий: вся жидкость участвует в шаре.
    Ef берётся из fuel.Ef_fireball_kw_m2 (TNO Green Book, пропан ≈ 150 кВт/м²).
    """
    m_kg = float(ctx.intermediate.get("m_total_kg", 0.0))
    Ef = float(ctx.inputs["fuel"].get("Ef_fireball_kw_m2", 150.0))
    result = calc_fireball_by_M(m_kg=m_kg, Ef_kw_m2=Ef)
    ctx.results["fireball"] = result
    ctx.log(f"[fireball_bleve] m={m_kg:.2f} кг (весь объём резервуаров), Ef={Ef} кВт/м²")


def _run_jet_fire_tank(ctx: CalculationContext) -> None:
    """
    Струйный факел из вскипевшего СУГ (lpg).
    m_dot = m_flash / duration_s.
    Ef = 130 кВт/м² (ГОСТ Табл.Б.1, пропан).
    K = 13,5 — паровая фаза СУГ/СПГ (ГОСТ Р 12.3.047-2012, Прил. Б).
    Дополнительно: пиковый режим (m_dot_peak) для короткого начального выброса.
    """
    m_dot = float(ctx.intermediate.get("m_dot_kg_s", 0.0))
    m_dot_peak = float(ctx.intermediate.get("m_dot_peak_kg_s", m_dot))
    Ef = float(ctx.inputs["fuel"].get("Ef_jet_kw_m2", 130.0))
    K_vapor = 13.5

    steady = calc_jetfire_by_M(M_kg_s=m_dot, Ef_kw_m2=Ef, K=K_vapor)
    peak = calc_jetfire_by_M(M_kg_s=m_dot_peak, Ef_kw_m2=Ef, K=K_vapor)
    steady["peak"] = {
        "params": peak.get("params", {}),
        "table": peak.get("table", []),
        "zones": peak.get("zones", []),
    }
    ctx.results["jet_fire"] = steady
    ctx.log(
        f"[jet_fire_tank] m_dot_peak={m_dot_peak:.4f} кг/с, m_dot={m_dot:.4f} кг/с, "
        f"Ef={Ef} кВт/м², K={K_vapor}"
    )


# ── Списки модулей по топливу ─────────────────────────────────────────────────

_DIESEL_MODULES = [
    run_tank_mass,             # m_total
    run_diesel_evaporation,    # W, m_evap, m_cloud, E_J
    run_shockwave,             # ΔP(r), I+(r)          — ПЕРЕИСПОЛЬЗОВАНИЕ
    run_probit_zones,          # зоны стекло/здания/люди — ПЕРЕИСПОЛЬЗОВАНИЕ
    _run_fireball_from_cloud,  # огненный шар
    run_pool_fire,             # тепловое излучение пожара пролива
    run_people_exposure,       # число людей в зонах тепл. поражения
]

_LPG_MODULES = [
    run_tank_mass,             # m_total
    run_lpg_flash,             # m_flash, m_dot
    _run_jet_fire_tank,        # струйный факел
    _run_fireball_bleve,       # огненный шар BLEVE
    run_people_exposure,       # число людей в зонах тепл. поражения
]


# ── Сценарий ──────────────────────────────────────────────────────────────────

class TankParkScenario(BaseScenario):
    """
    Резервуарный парк — два физических pipeline в одном scenario_type.

    Pipeline выбирается по raw_inputs["fuel"]["id"]:
      "diesel" → ТВС + огненный шар + пожар пролива
      "lpg"    → струйный факел + огненный шар (BLEVE)
    """

    scenario_type = "tank_park"
    modules = []   # не используется напрямую — overriding run()

    def prepare(self, raw_inputs: Dict[str, Any]) -> CalculationContext:
        return CalculationContext(inputs=raw_inputs)

    def run(self, raw_inputs: Dict[str, Any]) -> "ScenarioResult":  # type: ignore[name-defined]
        """
        Переопределяем run() чтобы выбрать список модулей по топливу.

        Порядок:
          1. prepare()  — создать контекст
          2. validate() — базовая проверка входных данных
          3. выбрать modules[] по fuel_id
          4. запустить модули последовательно
        """
        from app.pipeline.models import ScenarioResult

        try:
            ctx = self.prepare(raw_inputs)
            ctx.set_scenario(self.scenario_type)
            self.validate(ctx)

            fuel_id = raw_inputs.get("fuel", {}).get("id", "diesel")
            modules = _DIESEL_MODULES if fuel_id == "diesel" else _LPG_MODULES

            ctx.log(f"[tank_park] топливо={fuel_id}, модулей={len(modules)}")
            for module_fn in modules:
                module_fn(ctx)

            return ScenarioResult(scenario_type=self.scenario_type, ctx=ctx)

        except Exception as exc:
            ctx = CalculationContext(inputs=raw_inputs)
            return ScenarioResult(
                scenario_type=self.scenario_type,
                ctx=ctx,
                error=str(exc),
            )

    def validate(self, ctx: CalculationContext) -> None:
        inp = ctx.inputs
        tank = inp.get("tank", {})
        spill = inp.get("spill", {})
        fuel = inp.get("fuel", {})

        errors = []
        if float(tank.get("volume_m3", 0.0)) <= 0:
            errors.append("tank.volume_m3 должен быть > 0")
        if int(tank.get("count", 0)) < 1:
            errors.append("tank.count должен быть >= 1")
        if float(spill.get("area_m2", 0.0)) <= 0:
            errors.append("spill.area_m2 должна быть > 0")
        if float(spill.get("duration_s", 0.0)) <= 0:
            errors.append("spill.duration_s должна быть > 0")
        if fuel.get("id") not in ("diesel", "lpg"):
            errors.append(f"fuel.id должен быть 'diesel' или 'lpg', получено: {fuel.get('id')!r}")

        if errors:
            from app.domain.base import ScenarioError
            raise ScenarioError("Ошибки входных данных tank_park:\n" + "\n".join(f"  - {e}" for e in errors))
