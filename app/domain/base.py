# app/domain/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, TYPE_CHECKING

from app.core.context import CalculationContext

if TYPE_CHECKING:
    from app.pipeline.models import ScenarioResult


class ScenarioError(ValueError):
    """Ошибка валидации входных данных сценария."""


class BaseScenario(ABC):
    """
    Базовый класс сценария аварии.

    Каждый сценарий:
      - знает свой тип (scenario_type)
      - хранит упорядоченный список модулей (modules)
      - сам подготавливает CalculationContext из raw_inputs (prepare)
      - может валидировать входные данные (validate)
      - запускает модули последовательно и возвращает ScenarioResult

    Добавить новый сценарий = создать подкласс + указать modules.
    """

    scenario_type: str
    modules: List[Callable[[CalculationContext], None]] = []

    @abstractmethod
    def prepare(self, raw_inputs: Dict[str, Any]) -> CalculationContext:
        """Превращает raw_inputs в CalculationContext (без побочных эффектов)."""

    def validate(self, ctx: CalculationContext) -> None:
        """
        Валидация перед расчётом.
        Бросает ScenarioError если данные некорректны.
        """

    def run(self, raw_inputs: Dict[str, Any]) -> "ScenarioResult":
        """
        Полный pipeline сценария:
          prepare → validate → [module_1, module_2, ...] → ScenarioResult
        """
        from app.pipeline.models import ScenarioResult

        try:
            ctx = self.prepare(raw_inputs)
            sid = raw_inputs.get("meta", {}).get("scenario_id", "")
            ctx.set_scenario(f"{self.scenario_type}_{sid}" if sid else self.scenario_type)
            self.validate(ctx)
            for module_fn in self.modules:
                module_fn(ctx)
            return ScenarioResult(scenario_type=self.scenario_type, ctx=ctx)
        except Exception as exc:
            ctx = CalculationContext(inputs=raw_inputs)
            return ScenarioResult(
                scenario_type=self.scenario_type,
                ctx=ctx,
                error=str(exc),
            )
