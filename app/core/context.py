# app/core/context.py
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class CalculationContext:
    """
    Единый контекст расчёта (воспроизводимость):
      inputs -> intermediate -> results (+ logs, validation)

    - inputs: исходные данные (ввод пользователя/сценария)
    - intermediate: промежуточные величины (как в методике 7.1)
    - results: итоговые массивы/радиусы/таблицы
    - validation: результаты сверки с ручным расчётом (опционально)
    - logs: протокол выполнения модулей
    """

    inputs: Dict[str, Any]
    intermediate: Dict[str, Any] = field(default_factory=dict)
    results: Dict[str, Any] = field(default_factory=dict)
    validation: Dict[str, Any] = field(default_factory=dict)
    logs: List[str] = field(default_factory=list)

    created_at: datetime = field(default_factory=datetime.utcnow)
    scenario_id: Optional[str] = None

    def log(self, msg: str) -> None:
        self.logs.append(msg)

    def set_scenario(self, scenario_id: str) -> None:
        self.scenario_id = scenario_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "created_at": self.created_at.isoformat(),
            "inputs": self.inputs,
            "intermediate": self.intermediate,
            "results": self.results,
            "validation": self.validation,
            "logs": self.logs,
        }