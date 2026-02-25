# app/report/word_builder.py
from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass
from typing import Any, Dict

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

from app.core.fuels import get_fuel


def _to_dict(obj: Any) -> Any:
    """Приводит dataclass/объект к dict рекурсивно, иначе возвращает как есть."""
    if obj is None:
        return None
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_dict(x) for x in obj]
    # обычный объект с атрибутами (на всякий случай)
    if hasattr(obj, "__dict__"):
        return {k: _to_dict(v) for k, v in vars(obj).items()}
    return obj


def build_context(project) -> Dict[str, Any]:
    """
    Собирает контекст для template.docx.
    Делает максимально “широкий” словарь, чтобы шаблон мог брать любые данные.
    """
    ctx: Dict[str, Any] = {
        "project": {
            "name": getattr(project, "name", ""),
            "object_name": getattr(project, "object_name", ""),
            "address": getattr(project, "address", ""),
        },
        "pouos": [],
    }

    pouos = getattr(project, "pouos", []) or []
    for p in pouos:
        fuel = get_fuel(getattr(p, "fuel_id", ""))  # get_fuel уже нормализует алиасы

        is_indoor = bool(getattr(p, "is_indoor", False))
        space_title = "Помещение" if is_indoor else "Открытая площадка"

        p_dict: Dict[str, Any] = {
            "code": getattr(p, "code", ""),
            "title": getattr(p, "title", ""),
            "is_indoor": is_indoor,
            "space_title": space_title,

            "fuel_id": getattr(fuel, "id", getattr(p, "fuel_id", "")),
            "fuel_title": getattr(fuel, "title", ""),

            # ✅ ключ, который у тебя ломался:
            "eud0_j_per_kg": getattr(fuel, "eud0_j_per_kg", 0.0),

            # входы/результаты/трубы
            "inputs": _to_dict(getattr(p, "inputs", {}) or {}),
            "results": _to_dict(getattr(p, "results", {}) or {}),
            "pipes": _to_dict(getattr(p, "pipes", []) or []),
        }

        ctx["pouos"].append(p_dict)

    return ctx


def _attach_images_for_docxtpl(doc: DocxTemplate, ctx: Dict[str, Any], image_keys: Dict[str, str] | None = None):
    """
    (Опционально) Подключение картинок в контекст.
    image_keys: {"fireball_chart": "pouos[0].results.fireball_chart_path"} — если захочешь.
    Сейчас оставлено как расширение.
    """
    # Пока ничего не делаем — чтобы не ломать текущий шаблон.
    # Когда будем вставлять графики 7.2, сюда добавим InlineImage.
    return


def render_report(template_path: str, output_path: str, project) -> None:
    """
    Рендерит Word по docxtpl-шаблону.
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Не найден шаблон: {template_path}")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    doc = DocxTemplate(template_path)
    ctx = build_context(project)

    # Если позже будем вставлять графики/картинки — подключим тут InlineImage
    _attach_images_for_docxtpl(doc, ctx)

    doc.render(ctx)
    doc.save(output_path)
