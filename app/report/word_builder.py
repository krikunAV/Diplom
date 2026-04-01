# app/report/word_builder.py
from __future__ import annotations

import os
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List

from docxtpl import DocxTemplate, InlineImage
from docx.shared import Mm

from app.core.fuels import get_fuel


def _to_dict(obj: Any) -> Any:
    """
    Рекурсивно приводит dataclass / объект к dict / list.

    Зачем это нужно:
    - часть данных в проекте может быть dataclass;
    - часть может быть обычным dict;
    - для docxtpl удобнее работать уже с обычными словарями и списками.
    """
    if obj is None:
        return None
    if is_dataclass(obj):
        return asdict(obj)
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_dict(x) for x in obj]
    if hasattr(obj, "__dict__"):
        return {k: _to_dict(v) for k, v in vars(obj).items()}
    return obj


def _round_if_number(v: Any, ndigits: int = 2) -> Any:
    """
    Если значение число — округляем.
    Если нет — возвращаем как есть.
    """
    if isinstance(v, (int, float)):
        return round(v, ndigits)
    return v


def _pretty_value(v: Any, ndigits: int = 2) -> str:
    """
    Красивое строковое представление значения для шаблона Word.
    """
    if v is None:
        return "не найдено"
    if isinstance(v, (int, float)):
        return str(round(v, ndigits))
    return str(v)


def _pretty_dict(d: Dict[str, Any], ndigits: int = 2) -> List[Dict[str, str]]:
    """
    Преобразует словарь в список словарей вида:
        [{"name": ..., "value": ...}, ...]

    Это удобно для циклов в docxtpl.
    """
    out = []
    for k, v in (d or {}).items():
        out.append({
            "name": str(k),
            "value": _pretty_value(v, ndigits),
        })
    return out


def _pretty_building_zones(d: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Подготовка зон повреждений зданий для Word.

    Ожидается, что зоны могут приходить как:
        "A": [r1, r2]
        "B": [r1, r2]
        ...

    Важная правка:
    если зона фактически отсутствует и расчёт дал [0.0, 0.0],
    то вместо "0.0–0.0 м" выводим "-".
    """
    out = []

    for k, v in (d or {}).items():
        if isinstance(v, (list, tuple)) and len(v) == 2:
            r1, r2 = v

            # Если границы зоны не определены
            if r1 is None or r2 is None:
                txt = "-"
            else:
                try:
                    r1f = float(r1)
                    r2f = float(r2)

                    # Если зона "нулевая", показываем прочерк
                    if r1f == 0.0 and r2f == 0.0:
                        txt = "-"
                    else:
                        r1s = _pretty_value(r1f)
                        r2s = _pretty_value(r2f)
                        txt = f"{r1s}–{r2s} м"
                except (TypeError, ValueError):
                    txt = _pretty_value(v)
        else:
            txt = _pretty_value(v)

        out.append({
            "name": str(k),
            "value": txt,
        })

    return out


def _pad_building_zones(zones: List[Dict[str, str]], target_len: int = 5) -> List[Dict[str, str]]:
    """
    Шаблон жёстко обращается к зонам так:
        p.tvs.zones_buildings[0]
        ...
        p.tvs.zones_buildings[4]

    Поэтому, если расчёт вернул меньше 5 зон,
    добиваем список заглушками, чтобы шаблон не падал.
    """
    out = list(zones or [])
    while len(out) < target_len:
        out.append({"name": "", "value": "-"})
    return out


def _safe_inline_image(doc: DocxTemplate, path: str, width_mm: int = 150):
    """
    Возвращает InlineImage, если файл существует.
    Если файла нет — возвращает None.

    Это позволяет в шаблоне писать:
        {% if p.tvs_dp_chart_img %}
        {{ p.tvs_dp_chart_img }}
        {% endif %}
    """
    if path and os.path.exists(path):
        return InlineImage(doc, path, width=Mm(width_mm))
    return None


def _build_release_block(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Подготовка блока release для шаблона Word.

    Здесь мы НЕ пересчитываем физику заново.
    Мы только:
    - берём уже рассчитанные значения из results["release"];
    - аккуратно округляем;
    - подготавливаем их под шаблон.
    """
    rel = (results or {}).get("release", {}) or {}

    return {
        "accident_pipe": rel.get("accident_pipe", ""),
        "P_up_kpa": _round_if_number(rel.get("P_up_kpa")),
        "P2_kpa": _round_if_number(rel.get("P2_kpa", rel.get("P_up_kpa"))),
        "d_hole_mm": _round_if_number(rel.get("d_hole_mm")),
        "d_m": _round_if_number(rel.get("d_m"), 4),
        "t_shutoff_s": _round_if_number(rel.get("t_shutoff_s")),

        "F_m2": _round_if_number(rel.get("F_m2"), 6),
        "v_g_m3_kg": _round_if_number(rel.get("v_g_m3_kg"), 6),
        "m_dot_kg_s": _round_if_number(rel.get("m_dot_kg_s", rel.get("G_kg_s")), 4),
        "M1T_kg": _round_if_number(rel.get("M1T_kg")),
        "sum_r2L_m3": _round_if_number(rel.get("sum_r2L_m3"), 6),
        "V2T_m3": _round_if_number(rel.get("V2T_m3")),
        "M2T_kg": _round_if_number(rel.get("M2T_kg")),
        "Mg_kg": _round_if_number(rel.get("Mg_kg")),
        "M_total_kg": _round_if_number(rel.get("M_total_kg", rel.get("Mg_kg"))),
        "m_cloud_kg": _round_if_number(rel.get("m_cloud_kg")),

        "Eud_J_kg": _round_if_number(rel.get("Eud_J_kg")),
        "E_concentration_correction": _round_if_number(rel.get("E_concentration_correction"), 6),
        "E_J": _round_if_number(rel.get("E_J")),
        "Z": _round_if_number(rel.get("Z"), 4),
        "rho_n_kg_m3": _round_if_number(rel.get("rho_n_kg_m3"), 4),
        "R0_J_kgK": _round_if_number(rel.get("R0_J_kgK"), 4),
        "T_K": _round_if_number(rel.get("T_K"), 2),

        # Поля, которые ждёт шаблон
        "L_wind1_m": _round_if_number(rel.get("L_wind1_m")),
        "L_wind3_m": _round_if_number(rel.get("L_wind3_m")),
        "r0_wind1_m": _round_if_number(rel.get("r0_wind1_m")),
        "r0_wind3_m": _round_if_number(rel.get("r0_wind3_m")),

        "skip_reason": rel.get("skip_reason"),
    }


def _build_jetfire_block(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Подготовка блока факельного горения.
    """
    jf = (results or {}).get("jet_fire", {}) or {}
    params = jf.get("params", {}) or {}

    table = []
    for row in (jf.get("table") or []):
        table.append({
            "r_m": _round_if_number(row.get("r_m")),
            "tau": _round_if_number(row.get("tau"), 6),
            "Fq": _round_if_number(row.get("Fq"), 6),
            "q_kw_m2": _round_if_number(row.get("q_kw_m2"), 4),
        })

    zones = []
    for z in (jf.get("zones") or []):
        zones.append({
            "q_thr_kw_m2": _round_if_number(z.get("q_thr_kw_m2"), 2),
            "r_m": _pretty_value(z.get("r_m")),
        })

    return {
        "params": {
            "M_kg_s": _round_if_number(params.get("M_kg_s"), 4),
            "LF_m": _round_if_number(params.get("LF_m"), 2),
            "DF_m": _round_if_number(params.get("DF_m"), 2),
            "Ef_kw_m2": _round_if_number(params.get("Ef_kw_m2"), 2),
        },
        "table": table,
        "zones": zones,
        "skip_reason": jf.get("skip_reason"),
    }


def _build_fireball_block(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Подготовка блока огненного шара.
    """
    fb = (results or {}).get("fireball", {}) or {}
    params = fb.get("params", {}) or {}

    table = []
    for row in (fb.get("table") or []):
        table.append({
            "r_m": _round_if_number(row.get("r_m")),
            "q_kw_m2": _round_if_number(row.get("q_kw_m2"), 4),
        })

    zones = []
    for z in (fb.get("zones") or []):
        zones.append({
            "q_thr_kw_m2": _round_if_number(z.get("q_thr_kw_m2"), 2),
            "r_m": _pretty_value(z.get("r_m")),
        })

    return {
        "params": {k: _round_if_number(v) for k, v in params.items()},
        "table": table,
        "zones": zones,
        "skip_reason": fb.get("skip_reason"),
    }


def _build_tvs_block(results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Подготовка блока ТВС.

    Важно:
    шаблон использует не только основные поля таблицы,
    но и probit-поля:
      - Pr_people
      - prob_people
      - Pr_full
      - prob_full
      - Pr_heavy
      - prob_heavy
    """
    tvs = (results or {}).get("tvs_explosion", {}) or {}

    inputs = tvs.get("inputs", {}) or {}
    intermediate = tvs.get("intermediate", {}) or {}
    res = tvs.get("results", {}) or {}
    table = tvs.get("table", []) or []

    tvs_table = []
    for row in table:
        tvs_table.append({
            "r_m": _round_if_number(row.get("r_m")),
            "Rx": _round_if_number(row.get("Rx"), 6),
            "Px": _round_if_number(row.get("Px"), 6),
            "Ix": _round_if_number(row.get("Ix"), 6),
            "deltaP_Pa": _round_if_number(row.get("deltaP_Pa"), 4),
            "deltaP_kPa": _round_if_number(row.get("deltaP_kPa"), 4),
            "Iplus_Pa_s": _round_if_number(row.get("Iplus_Pa_s"), 6),

            "Pr_people": _round_if_number(row.get("Pr_people"), 4),
            "prob_people": _round_if_number(row.get("prob_people"), 2),

            "Pr_full": _round_if_number(row.get("Pr_full"), 4),
            "prob_full": _round_if_number(row.get("prob_full"), 2),

            "Pr_heavy": _round_if_number(row.get("Pr_heavy"), 4),
            "prob_heavy": _round_if_number(row.get("prob_heavy"), 2),
        })

    max_delta_p_kpa = None
    max_delta_r_m = None
    if tvs_table:
        max_row = max(tvs_table, key=lambda r: r.get("deltaP_Pa") or 0.0)
        max_delta_p_kpa = _round_if_number((max_row.get("deltaP_Pa") or 0.0) / 1000.0, 4)
        max_delta_r_m = max_row.get("r_m")

    zones_buildings = _pad_building_zones(
        _pretty_building_zones(res.get("zones_buildings", {})),
        5,
    )

    return {
        "inputs": _to_dict(inputs),
        "intermediate": {
            k: _round_if_number(v, 6)
            for k, v in intermediate.items()
            if not isinstance(v, (list, dict, tuple))
        },
        "results": _to_dict(res),
        "logs": tvs.get("logs", []) or [],
        "table": tvs_table,

        "max_delta_p_kpa": max_delta_p_kpa,
        "max_delta_r_m": max_delta_r_m,

        "zones_glass": _pretty_dict(res.get("zones_glass", {})),
        "zones_people": _pretty_dict(res.get("zones_people", {})),
        "zones_buildings": zones_buildings,

        "flame_speed_m_s": _round_if_number(tvs.get("flame_speed_m_s"), 4),
        "pr4_r0": _round_if_number(tvs.get("pr4_r0"), 4),

        "skip_reason": tvs.get("skip_reason"),
    }


def build_context(project, doc: DocxTemplate | None = None) -> Dict[str, Any]:
    """
    Собирает итоговый контекст для шаблона Word.

    Здесь:
    - читаем project и все его pouos;
    - приводим всё к обычным dict/list;
    - подготавливаем блоки release / tvs / jet_fire / fireball;
    - подготавливаем список труб в удобном для шаблона виде;
    - добавляем пути и InlineImage для графиков.
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
        fuel = get_fuel(getattr(p, "fuel_id", ""))

        is_indoor = bool(getattr(p, "is_indoor", False))
        space_title = "Помещение" if is_indoor else "Открытая площадка"

        raw_inputs = _to_dict(getattr(p, "inputs", {}) or {})
        raw_results = _to_dict(getattr(p, "results", {}) or {})
        raw_pipes = _to_dict(getattr(p, "pipes", []) or [])

        # ---------------- Подготовка труб для шаблона ----------------
        # В шаблоне используется pipe.d_inner_m,
        # но в исходных объектах чаще всего есть только diameter_mm.
        # Поэтому создаём подготовленный список труб.
        prepared_pipes = []
        for pipe in raw_pipes:
            diameter_mm = pipe.get("diameter_mm")
            d_inner_m = None

            if diameter_mm is not None:
                try:
                    d_inner_m = round(float(diameter_mm) / 1000.0, 3)
                except (TypeError, ValueError):
                    d_inner_m = None

            prepared_pipes.append({
                **pipe,
                "d_inner_m": d_inner_m,
                "length_m": pipe.get("length_m"),
            })

        # ---------------- Подготовка расчётных блоков ----------------
        release_block = _build_release_block(raw_results)
        jetfire_block = _build_jetfire_block(raw_results)
        fireball_block = _build_fireball_block(raw_results)
        tvs_block = _build_tvs_block(raw_results)

        code = getattr(p, "code", "")
        charts_dir = os.path.join("out", "charts")

        tvs_dp_path = os.path.join(charts_dir, f"tvs_dp_{code}.png")
        tvs_imp_path = os.path.join(charts_dir, f"tvs_imp_{code}.png")
        jetfire_path = os.path.join(charts_dir, f"jetfire_{code}.png")
        fireball_path = os.path.join(charts_dir, f"fireball_{code}.png")

        p_dict: Dict[str, Any] = {
            "code": code,
            "title": getattr(p, "title", ""),
            "is_indoor": is_indoor,
            "space_title": space_title,

            "fuel_id": getattr(fuel, "id", getattr(p, "fuel_id", "")),
            "fuel_title": getattr(fuel, "title", ""),
            "eud0_j_per_kg": getattr(fuel, "eud0_j_per_kg", 0.0),

            # Сырой слой
            "inputs": raw_inputs,
            "results": raw_results,

            # Подготовленные трубы для таблицы Word
            "pipes": prepared_pipes,

            # Подготовленные блоки расчёта
            "release": release_block,
            "jet_fire": jetfire_block,
            "fireball": fireball_block,
            "tvs": tvs_block,

            # Пути к графикам
            "tvs_dp_chart_path": tvs_dp_path,
            "tvs_imp_chart_path": tvs_imp_path,
            "jetfire_chart_path": jetfire_path,
            "fireball_chart_path": fireball_path,

            # Флаги для шаблона
            "has_release": bool(release_block and not release_block.get("skip_reason")),
            "has_jet_fire": bool(jetfire_block and not jetfire_block.get("skip_reason")),
            "has_fireball": bool(fireball_block and not fireball_block.get("skip_reason")),
            "has_tvs": bool(tvs_block and not tvs_block.get("skip_reason")),
            "has_error": bool(raw_results.get("error")),
            "error_text": raw_results.get("error"),
        }

        # Если передан doc — подцепляем картинки как InlineImage
        if doc is not None:
            p_dict["tvs_dp_chart_img"] = _safe_inline_image(doc, tvs_dp_path, width_mm=150)
            p_dict["tvs_imp_chart_img"] = _safe_inline_image(doc, tvs_imp_path, width_mm=150)
            p_dict["jetfire_chart_img"] = _safe_inline_image(doc, jetfire_path, width_mm=150)
            p_dict["fireball_chart_img"] = _safe_inline_image(doc, fireball_path, width_mm=150)

        ctx["pouos"].append(p_dict)

    return ctx


def render_report(template_path: str, output_path: str, project) -> None:
    """
    Рендерит Word-файл по шаблону docxtpl.
    """
    if not os.path.exists(template_path):
        raise FileNotFoundError(f"Не найден шаблон: {template_path}")

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)

    logger.debug("Загружаем шаблон: %s", template_path)
    doc = DocxTemplate(template_path)

    logger.debug("Строим контекст для docxtpl")
    ctx = build_context(project, doc=doc)

    logger.debug("Рендерим шаблон")
    doc.render(ctx)

    logger.debug("Сохраняем: %s", output_path)
    doc.save(output_path)

    logger.debug("Отчёт сохранён")