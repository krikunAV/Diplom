# app/pipeline/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.core.context import CalculationContext
from app.core.models import PipeRow


# ── Результат одного сценария ─────────────────────────────────────────────────

@dataclass
class ScenarioResult:
    """
    Результат выполнения одного сценария (TVS / jet_fire / fireball / ...).

    ok == True  → расчёт прошёл без ошибок
    ok == False → в error описание проблемы, ctx частично заполнен
    """
    scenario_type: str
    ctx: CalculationContext
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None


# ── Входные данные ПООУ ───────────────────────────────────────────────────────

@dataclass
class POUOInput:
    """
    Входные данные для одного ПООУ (потенциально опасного участка).
    Используется вместо legacy POUO-модели как чистый value object.
    """
    code: str
    title: str
    fuel_id: str
    is_indoor: bool = False
    inputs: Dict[str, Any] = field(default_factory=dict)
    pipes: List[PipeRow] = field(default_factory=list)


# ── Результат расчёта ПООУ ────────────────────────────────────────────────────

@dataclass
class POUOResult:
    """
    Результат расчёта одного ПООУ.
    Содержит результаты всех сценариев, которые были запущены.

    Ключи словаря scenarios:
      "tvs_explosion", "jet_fire", "fireball", "indoor", "error", "skip"
    """
    pouo_input: POUOInput
    scenarios: Dict[str, ScenarioResult] = field(default_factory=dict)

    @property
    def tvs(self) -> Optional[ScenarioResult]:
        return self.scenarios.get("tvs_explosion")

    @property
    def jet_fire(self) -> Optional[ScenarioResult]:
        return self.scenarios.get("jet_fire")

    @property
    def fireball(self) -> Optional[ScenarioResult]:
        return self.scenarios.get("fireball")

    @property
    def has_error(self) -> bool:
        return any(not r.ok for r in self.scenarios.values())


# ── Входные данные проекта ────────────────────────────────────────────────────

@dataclass
class ProjectInput:
    name: str
    object_name: str
    address: str
    pouos: List[POUOInput] = field(default_factory=list)


# ── Результат проекта ─────────────────────────────────────────────────────────

@dataclass
class ProjectResult:
    """
    Итоговый результат расчёта всего проекта.
    Итоговый отчёт = сумма всех POUOResult.
    """
    project_input: ProjectInput
    pouo_results: List[POUOResult] = field(default_factory=list)
