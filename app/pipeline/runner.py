# app/pipeline/runner.py
from __future__ import annotations

from app.core.context import CalculationContext
from app.core.models import POUO, Project
from app.domain.registry import get_scenario
from app.pipeline.config import EngineConfig
from app.pipeline.models import POUOInput, POUOResult, ProjectInput, ProjectResult, ScenarioResult
from app.pipeline.recipes import get_recipe


def run_pouo(
    pouo: POUOInput,
    cfg: EngineConfig | None = None,
    fail_fast: bool = True,
) -> POUOResult:
    """
    Универсальный runner для одного ПООУ.

    Не знает ни о каких конкретных сценариях.
    Перебирает pouo.scenario_configs и для каждого:
      1. проверяет sc.requires — все нужные ключи должны быть в accumulated
      2. строит raw_inputs через sc.build_inputs(pouo, cfg, accumulated)
      3. запускает get_scenario(sc.scenario_type).run(raw_inputs)
      4. обновляет accumulated, защищая от перезаписи существующих ключей
      5. проверяет sc.provides — все обещанные ключи должны появиться в accumulated

    fail_fast=True  (по умолчанию): первая ошибка прерывает цепочку.
    fail_fast=False: все сценарии выполняются независимо, каждый получает
                     свою запись об ошибке.
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

        # ── 1. Проверка requires ──────────────────────────────────────────────
        missing_req = sc.requires - accumulated.keys()
        if missing_req:
            result.scenarios[sc.scenario_type] = ScenarioResult(
                scenario_type=sc.scenario_type,
                ctx=CalculationContext(inputs=pouo.inputs),
                error=(
                    f"Сценарий '{sc.scenario_type}' требует ключи "
                    f"{sorted(missing_req)} в accumulated, но они отсутствуют. "
                    f"Вероятно, предыдущий сценарий завершился с ошибкой."
                ),
            )
            if fail_fast:
                break
            continue

        # ── 2. Подготовка входных данных ─────────────────────────────────────
        try:
            raw_inputs = sc.build_inputs(pouo, cfg, accumulated)
        except Exception as exc:
            result.scenarios[sc.scenario_type] = ScenarioResult(
                scenario_type=sc.scenario_type,
                ctx=CalculationContext(inputs=pouo.inputs),
                error=str(exc),
            )
            if fail_fast:
                break
            continue

        # ── 3. Выполнение сценария ────────────────────────────────────────────
        sr = get_scenario(sc.scenario_type).run(raw_inputs)
        result.scenarios[sc.scenario_type] = sr

        if not sr.ok:
            if fail_fast:
                break
            continue

        # ── 4 & 5. Обновление accumulated + проверка provides ────────────────
        # В accumulated попадают ТОЛЬКО ключи, объявленные в sc.provides.
        # Это намеренно: jet_fire и fireball оба пишут 'params'/'table'/'zones'
        # в ctx.results, но ни один из них не объявляет эти ключи в provides —
        # их данные нужны только отчёту, а не следующим сценариям.
        if sc.provides:
            merged = {**sr.ctx.intermediate, **sr.ctx.results}

            # Защита от перезаписи — только для ключей из provides
            conflicts = sc.provides & accumulated.keys()
            if conflicts:
                result.scenarios[sc.scenario_type] = ScenarioResult(
                    scenario_type=sc.scenario_type,
                    ctx=sr.ctx,
                    error=(
                        f"Сценарий '{sc.scenario_type}' пытается перезаписать "
                        f"уже существующие ключи в accumulated: {sorted(conflicts)}. "
                        f"Проверьте provides в рецепте."
                    ),
                )
                if fail_fast:
                    break
                continue

            # Проверка: все обещанные ключи должны присутствовать в ctx
            missing_prov = sc.provides - merged.keys()
            if missing_prov:
                result.scenarios[sc.scenario_type] = ScenarioResult(
                    scenario_type=sc.scenario_type,
                    ctx=sr.ctx,
                    error=(
                        f"Сценарий '{sc.scenario_type}' должен предоставить "
                        f"{sorted(missing_prov)}, но не сделал этого. "
                        f"Проверьте, что все ключи из provides записываются "
                        f"в ctx.intermediate или ctx.results."
                    ),
                )
                if fail_fast:
                    break
                continue

            # Добавляем в accumulated только объявленные ключи
            for key in sc.provides:
                accumulated[key] = merged[key]

    return result


def run_project(
    project: ProjectInput,
    cfg: EngineConfig | None = None,
    fail_fast: bool = True,
) -> ProjectResult:
    """Запускает расчёт для всего проекта последовательно."""
    cfg = cfg or EngineConfig()
    pr = ProjectResult(project_input=project)
    for pouo in project.pouos:
        pr.pouo_results.append(run_pouo(pouo, cfg, fail_fast=fail_fast))
    return pr


# ── Конвертеры legacy-моделей ─────────────────────────────────────────────────

def pouo_to_input(p: POUO) -> POUOInput:
    """
    Конвертирует legacy POUO → POUOInput.
    Рецепт подбирается по fuel_id, is_indoor И scenario_code (p.code).
    scenario_code нужен чтобы отличить POUO1 (резервуарный парк)
    от других сценариев с diesel/lpg.
    """
    return POUOInput(
        code=p.code,
        title=p.title,
        fuel_id=p.fuel_id,
        is_indoor=p.is_indoor,
        inputs=dict(p.inputs),
        pipes=list(p.pipes),
        scenario_configs=get_recipe(p.fuel_id, p.is_indoor, scenario_code=p.code),
    )


def project_to_input(project: Project) -> ProjectInput:
    """Конвертирует legacy Project → ProjectInput."""
    return ProjectInput(
        name=project.name,
        object_name=project.object_name,
        address=project.address,
        pouos=[pouo_to_input(p) for p in project.pouos],
    )
