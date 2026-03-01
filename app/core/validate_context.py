# app/core/validate_context.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Union

from app.core.context_spec import CONTEXT_SPEC


@dataclass
class ValidationError:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


Number = Union[int, float]


def _is_number(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _validate_value_type(value: Any, expected_type: str) -> bool:
    if expected_type == "str":
        return isinstance(value, str)
    if expected_type == "number":
        return _is_number(value)
    if expected_type == "list":
        return isinstance(value, list)
    if expected_type == "dict":
        return isinstance(value, dict)
    # fallback: unknown type string => accept
    return True


def validate_inputs_structure(inputs: Dict[str, Any], spec: Dict[str, Any] = None) -> List[ValidationError]:
    """
    Проверка структуры и обязательных ключей inputs по CONTEXT_SPEC["inputs"].
    Возвращает список ValidationError. Пустой список => OK.
    """
    if spec is None:
        spec = CONTEXT_SPEC["inputs"]

    errors: List[ValidationError] = []

    if not isinstance(inputs, dict):
        return [ValidationError("inputs", "must be a dict")]

    def walk(node: Any, node_spec: Any, path: str) -> None:
        # node_spec может быть:
        # - dict со вложенными ключами (группа)
        # - dict с полями {"type": ..., "required": ...} (лист)
        # - list-spec (pipes)
        if isinstance(node_spec, dict) and "type" in node_spec:
            # листовой узел или list-узел
            expected_type = node_spec.get("type", "unknown")
            required = bool(node_spec.get("required", False))

            if required and node is None:
                errors.append(ValidationError(path, "is required"))
                return

            # если не требуется и отсутствует — ок
            if node is None:
                return

            if expected_type == "list":
                if not isinstance(node, list):
                    errors.append(ValidationError(path, f"must be list, got {type(node).__name__}"))
                    return
                # pipes: items spec может быть dict
                items_spec = node_spec.get("items")
                items_type = node_spec.get("items_type")
                if items_spec is not None:
                    for i, item in enumerate(node):
                        if not isinstance(item, dict):
                            errors.append(ValidationError(f"{path}[{i}]", "must be dict"))
                            continue
                        for k, v in items_spec.items():
                            child = item.get(k)
                            if v.get("required", False) and child is None:
                                errors.append(ValidationError(f"{path}[{i}].{k}", "is required"))
                                continue
                            if child is not None and not _validate_value_type(child, v.get("type", "unknown")):
                                errors.append(ValidationError(
                                    f"{path}[{i}].{k}",
                                    f"wrong type, expected {v.get('type')}, got {type(child).__name__}"
                                ))
                elif items_type is not None:
                    for i, item in enumerate(node):
                        if items_type == "number" and not _is_number(item):
                            errors.append(ValidationError(f"{path}[{i}]", "must be number"))
                        if items_type == "str" and not isinstance(item, str):
                            errors.append(ValidationError(f"{path}[{i}]", "must be str"))
                return

            # обычные типы
            if not _validate_value_type(node, expected_type):
                errors.append(ValidationError(path, f"wrong type, expected {expected_type}, got {type(node).__name__}"))
            return

        # группа ключей
        if not isinstance(node_spec, dict):
            return

        if not isinstance(node, dict):
            errors.append(ValidationError(path, f"must be dict, got {type(node).__name__}"))
            return

        for key, child_spec in node_spec.items():
            child_path = f"{path}.{key}" if path else key
            if isinstance(child_spec, dict) and "type" in child_spec:
                required = bool(child_spec.get("required", False))
                value = node.get(key)
                if required and key not in node:
                    errors.append(ValidationError(child_path, "is required"))
                    continue
                # validate leaf/list
                walk(value, child_spec, child_path)
            else:
                # nested group
                if key not in node:
                    # nested group is required if it contains required leaves, но проще: считаем group required
                    errors.append(ValidationError(child_path, "group is required"))
                    continue
                walk(node.get(key), child_spec, child_path)

    walk(inputs, spec, "inputs")
    return errors


def validate_inputs_semantics(inputs: Dict[str, Any]) -> List[ValidationError]:
    """
    Минимальная семантическая валидация (диапазоны), чтобы ловить очевидные ошибки.
    Не привязана к конкретным формулам — подходит для прототипа/ФСИ.
    """
    e: List[ValidationError] = []

    def get(path: Tuple[str, ...]) -> Any:
        cur: Any = inputs
        for p in path:
            if not isinstance(cur, dict) or p not in cur:
                return None
            cur = cur[p]
        return cur

    # release
    d = get(("release", "orifice_d_m"))
    if _is_number(d) and d <= 0:
        e.append(ValidationError("inputs.release.orifice_d_m", "must be > 0"))

    mu = get(("release", "mu"))
    if _is_number(mu) and not (0 < mu <= 1.5):
        e.append(ValidationError("inputs.release.mu", "expected (0, 1.5]"))

    psi = get(("release", "psi"))
    if _is_number(psi) and not (0 < psi <= 1.5):
        e.append(ValidationError("inputs.release.psi", "expected (0, 1.5]"))

    Pg = get(("release", "Pg_Pa"))
    if _is_number(Pg) and Pg <= 0:
        e.append(ValidationError("inputs.release.Pg_Pa", "must be > 0"))

    T = get(("release", "T_K"))
    if _is_number(T) and T <= 0:
        e.append(ValidationError("inputs.release.T_K", "must be > 0"))

    R0 = get(("release", "R0_J_kgK"))
    if _is_number(R0) and R0 <= 0:
        e.append(ValidationError("inputs.release.R0_J_kgK", "must be > 0"))

    t_off = get(("release", "t_shutoff_s"))
    if _is_number(t_off) and t_off <= 0:
        e.append(ValidationError("inputs.release.t_shutoff_s", "must be > 0"))

    # env
    Z = get(("cloud", "Z"))
    if _is_number(Z) and not (0 <= Z <= 1):
        e.append(ValidationError("inputs.cloud.Z", "must be in [0, 1]"))

    mode = get(("shockwave", "explosion_mode"))
    if isinstance(mode, str) and mode not in ("detonation", "deflagration"):
        e.append(ValidationError("inputs.shockwave.explosion_mode", "must be 'detonation' or 'deflagration'"))

    r_grid = get(("shockwave", "r_grid_m"))
    if isinstance(r_grid, list) and len(r_grid) == 0:
        e.append(ValidationError("inputs.shockwave.r_grid_m", "must be non-empty list"))

    # pipes
    pipes = get(("isolated_section", "pipes"))
    if isinstance(pipes, list) and len(pipes) == 0:
        e.append(ValidationError("inputs.isolated_section.pipes", "must be non-empty list"))

    return e


def validate_context_inputs(inputs: Dict[str, Any]) -> List[ValidationError]:
    """
    Единая функция: структурная + семантическая проверка inputs.
    """
    errors = []
    errors.extend(validate_inputs_structure(inputs))
    # семантику проверяем только если структура в целом ок,
    # иначе будут каскадные ошибки
    if not errors:
        errors.extend(validate_inputs_semantics(inputs))
    return errors