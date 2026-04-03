# app/pipeline/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, FrozenSet, List, Optional

from app.core.context import CalculationContext
from app.core.models import PipeRow


# ── Конфигурация одного сценария ─────────────────────────────────────────────

@dataclass
class ScenarioConfig:
    """
    Описание сценария для конкретного ПООУ.

    scenario_type   — ключ в SCENARIO_REGISTRY
    build_inputs    — функция, которая строит raw_inputs для сценария.

    Сигнатура build_inputs:
        (pouo: POUOInput, cfg: EngineConfig, accumulated: dict) -> dict

    accumulated — накопленный словарь intermediate+results из уже
    выполненных сценариев. Позволяет jet_fire/fireball использовать
    m_dot/Mg из TVS без прямой зависимости между классами.

    requires — ключи, которые должны присутствовать в accumulated
               до запуска этого сценария. Runner проверяет их явно
               и выбрасывает ошибку вместо молчаливого падения.

    provides — ключи, которые сценарий гарантированно добавит
               в accumulated после успешного выполнения.
               Используются как документация контракта; runner
               не проверяет выход — только вход.
    """
    scenario_type: str
    build_inputs: Callable[["POUOInput", Any, dict], dict]
    requires: FrozenSet[str] = field(default_factory=frozenset)
    provides: FrozenSet[str] = field(default_factory=frozenset)


# ── Результат одного сценария ─────────────────────────────────────────────────

@dataclass
class ScenarioResult:
    """
    Результат выполнения одного сценария.

    ok == True  → расчёт прошёл без ошибок
    ok == False → error содержит описание, ctx частично заполнен
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
    Входные данные для одного ПООУ (чистый value object).

    scenario_configs — упорядоченный список сценариев, которые runner
    выполнит последовательно. Заполняется через recipes.py при создании
    объекта (например, через pouo_to_input).
    """
    code: str
    title: str
    fuel_id: str
    is_indoor: bool = False
    inputs: Dict[str, Any] = field(default_factory=dict)
    pipes: List[PipeRow] = field(default_factory=list)
    scenario_configs: List[ScenarioConfig] = field(default_factory=list)


# ── Результат расчёта ПООУ ────────────────────────────────────────────────────

@dataclass
class POUOResult:
    """
    Результат расчёта одного ПООУ.

    scenarios — словарь {scenario_type: ScenarioResult}.
    Ключи определяются списком scenario_configs, переданным в runner.
    """
    pouo_input: POUOInput
    scenarios: Dict[str, ScenarioResult] = field(default_factory=dict)

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
    """Итоговый результат расчёта всего проекта."""
    project_input: ProjectInput
    pouo_results: List[POUOResult] = field(default_factory=list)
