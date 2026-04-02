# app/pipeline/runner.py
from __future__ import annotations

from app.core.context import CalculationContext
from app.core.models import POUO, Project
from app.domain.registry import get_scenario
from app.pipeline.config import EngineConfig
from app.pipeline.models import POUOInput, POUOResult, ProjectInput, ProjectResult, ScenarioResult
from app.pipeline.recipes import get_recipe


def run_pouo(pouo: POUOInput, cfg: EngineConfig | None = None) -> POUOResult:
    """
    Универсальный runner для одного ПООУ.

    Не знает ни о каких конкретных сценариях.
    Перебирает pouo.scenario_configs и для каждого:
      1. строит raw_inputs через sc.build_inputs(pouo, cfg, accumulated)
      2. запускает get_scenario(sc.scenario_type).run(raw_inputs)
      3. накапливает intermediate + results для следующих сценариев
    """
    cfg = cfg or EngineConfig()
    result = POUOResult(pouo_input=pouo)

    if not pouo.scenario_configs:
        ctx = CalculationContext(inputs=pouo.inputs)
        result.scenarios["skip"] = ScenarioResult(
            scenario_type="skip",
            ctx=ctx,
            error=(
                "Indoor-сценарий пока не реализован."
                if pouo.is_indoor
                else f"Нет рецепта для топлива '{pouo.fuel_id}'."
            ),
        )
        return result

    # accumulated: промежуточные данные, доступные следующим сценариям
    accumulated: dict = {}

    for sc in pouo.scenario_configs:
        try:
            raw_inputs = sc.build_inputs(pouo, cfg, accumulated)
        except Exception as exc:
            ctx = CalculationContext(inputs=pouo.inputs)
            result.scenarios[sc.scenario_type] = ScenarioResult(
                scenario_type=sc.scenario_type, ctx=ctx, error=str(exc)
            )
            break  # ошибка подготовки данных — дальше не считаем

        sr = get_scenario(sc.scenario_type).run(raw_inputs)
        result.scenarios[sc.scenario_type] = sr

        if sr.ok:
            accumulated.update(sr.ctx.intermediate)
            accumulated.update(sr.ctx.results)

    return result


def run_project(
    project: ProjectInput,
    cfg: EngineConfig | None = None,
) -> ProjectResult:
    """Запускает расчёт для всего проекта последовательно."""
    cfg = cfg or EngineConfig()
    pr = ProjectResult(project_input=project)
    for pouo in project.pouos:
        pr.pouo_results.append(run_pouo(pouo, cfg))
    return pr


# ── Конвертеры legacy-моделей ─────────────────────────────────────────────────

def pouo_to_input(p: POUO) -> POUOInput:
    """
    Конвертирует legacy POUO → POUOInput.
    Рецепт (список ScenarioConfig) подбирается автоматически по fuel_id и is_indoor.
    """
    return POUOInput(
        code=p.code,
        title=p.title,
        fuel_id=p.fuel_id,
        is_indoor=p.is_indoor,
        inputs=dict(p.inputs),
        pipes=list(p.pipes),
        scenario_configs=get_recipe(p.fuel_id, p.is_indoor),
    )


def project_to_input(project: Project) -> ProjectInput:
    """Конвертирует legacy Project → ProjectInput."""
    return ProjectInput(
        name=project.name,
        object_name=project.object_name,
        address=project.address,
        pouos=[pouo_to_input(p) for p in project.pouos],
    )
