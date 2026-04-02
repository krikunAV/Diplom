# app/ui_tk/debug_output.py
"""
Форматирование подробного вывода результатов расчётов
по пунктам 7.1, 7.2 и 7.3 для проверки пользователем.

Функция build_calculation_debug_output(results) принимает
p.results одного ПОУО и возвращает готовый текст.
"""
from __future__ import annotations

from typing import Any
from app.core.calcs.tvs.probit_zones import ZONE_ABSENT


def _fmt_zone(val) -> str:
    """
    Форматирует одно значение радиуса зоны:
      ZONE_ABSENT ("-") → "не реализуется"
      None             → "> 200 м"
      float            → "XX.X м"
    """
    if val == ZONE_ABSENT:
        return "не реализуется"
    if val is None:
        return "> 200 м"
    try:
        return f"{float(val):.1f} м"
    except (TypeError, ValueError):
        return str(val)


def _fmt(value: Any, decimals: int = 4, unit: str = "") -> str:
    """Форматирует число или возвращает '—' если None/0."""
    if value is None:
        return "—"
    try:
        f = float(value)
        if decimals == 0:
            s = f"{f:,.0f}".replace(",", " ")
        elif f != 0 and abs(f) >= 1e6:
            s = f"{f:.4e}"
        else:
            s = f"{f:.{decimals}f}"
        return f"{s} {unit}".strip() if unit else s
    except (TypeError, ValueError):
        return str(value)


def _line(label: str, value: Any, decimals: int = 4, unit: str = "", width: int = 36) -> str:
    formatted = _fmt(value, decimals, unit)
    return f"    {label:<{width}} {formatted}"


def _zone_rows(zones: list | None) -> list[str]:
    if not zones:
        return ["    (зоны не определены)"]
    lines = []
    for z in zones:
        q = z.get("q_thr_kw_m2")
        r = z.get("r_m")
        r_str = f"{r:.1f} м" if r is not None else "не достигается"
        lines.append(f"    q = {q:<5} кВт/м²  →  r = {r_str}")
    return lines


def _section_71(rel: dict, tvs: dict) -> list[str]:
    lines = []
    lines.append("──── П.7.1. Выброс и ТВС-взрыв " + "─" * 40)
    lines.append("")

    # --- Входные параметры ---
    lines.append("  Входные параметры:")
    lines.append(_line("Аварийный участок:", rel.get("accident_pipe"), unit=""))
    lines.append(_line("Давление P0:", rel.get("P_up_kpa", rel.get("P2_kpa")), decimals=1, unit="кПа"))
    lines.append(_line("Диаметр отверстия:", rel.get("d_hole_mm"), decimals=1, unit="мм"))
    lines.append(_line("Время до отсечки:", rel.get("t_shutoff_s"), decimals=1, unit="с"))
    lines.append("")

    # --- Промежуточные расчёты выброса ---
    lines.append("  Промежуточные расчёты (выброс):")
    lines.append(_line("Площадь отверстия F:", rel.get("F_m2"), decimals=6, unit="м²"))
    lines.append(_line("Уд. объём газа v_g:", rel.get("v_g_m3_kg"), decimals=6, unit="м³/кг"))
    lines.append(_line("Массовый расход ṁ:", rel.get("m_dot_kg_s"), decimals=4, unit="кг/с"))
    lines.append(_line("Масса стр. выброса M1T:", rel.get("M1T_kg"), decimals=2, unit="кг"))
    lines.append(_line("Сумма r²·L участков:", rel.get("sum_r2L_m3"), decimals=6, unit="м³"))
    lines.append(_line("Объём газа в уч-ке V2T:", rel.get("V2T_m3"), decimals=2, unit="м³"))
    lines.append(_line("Масса газа в уч-ке M2T:", rel.get("M2T_kg"), decimals=2, unit="кг"))
    lines.append(_line("Суммарная масса Mг:", rel.get("Mg_kg"), decimals=2, unit="кг"))
    lines.append("")

    # --- Облако ---
    lines.append("  Облако ТВС:")
    lines.append(_line("Коэф. участия в облаке Z:", rel.get("Z"), decimals=2))
    lines.append(_line("Масса облака m_cloud:", rel.get("m_cloud_kg"), decimals=2, unit="кг"))
    lines.append(_line("Удельная энергия Eud:", rel.get("Eud_J_kg"), decimals=0, unit="Дж/кг"))
    lines.append(_line("Поправка конц. (Cg/Cst):", rel.get("E_concentration_correction"), decimals=4))
    lines.append(_line("Энергозапас взрыва E:", rel.get("E_J"), decimals=4, unit="Дж"))
    lines.append("")

    # --- Зоны ветрового рассеивания ---
    lines.append("  Зоны ветрового рассеивания:")
    lines.append(_line("Дальн. зона L (w=1 м/с):", rel.get("L_wind1_m"), decimals=1, unit="м"))
    lines.append(_line("Дальн. зона L (w=3 м/с):", rel.get("L_wind3_m"), decimals=1, unit="м"))
    lines.append(_line("Ближн. зона r0 (w=1 м/с):", rel.get("r0_wind1_m"), decimals=1, unit="м"))
    lines.append(_line("Ближн. зона r0 (w=3 м/с):", rel.get("r0_wind3_m"), decimals=1, unit="м"))
    lines.append("")

    # --- Ударная волна (из tvs) ---
    if isinstance(tvs, dict):
        intermediate = tvs.get("intermediate") or {}
        results = tvs.get("results") or {}
        table = tvs.get("table") or []

        lines.append("  Ударная волна ТВС:")
        lines.append(_line("Скорость пламени Vg:", tvs.get("flame_speed_m_s"), decimals=2, unit="м/с"))

        shock = results.get("shockwave_params") or {}
        lines.append(_line("Rx (приведённое расст.):", intermediate.get("Rx_ref"), decimals=4))
        lines.append(_line("E (из intermediate):", intermediate.get("E_J"), decimals=4, unit="Дж"))

        if table:
            max_row = max(table, key=lambda r: r.get("deltaP_Pa", 0.0))
            lines.append(_line(
                "max ΔP:",
                round(max_row.get("deltaP_Pa", 0.0) / 1000.0, 3),
                decimals=3, unit=f"кПа  при r = {max_row.get('r_m')} м"
            ))

        lines.append("")

        # Зоны поражения взрыва
        lines.append("  Зоны поражения (ТВС-взрыв):")

        _GLASS_LABELS = {
            "glass_5_10_kPa": "Остекление (5–10 кПа)",
            "glass_2_5_kPa":  "Остекление (2–5 кПа)",
            "glass_1_2_kPa":  "Остекление (1–2 кПа)",
        }
        zones_glass = results.get("zones_glass")
        if zones_glass:
            for key, label in _GLASS_LABELS.items():
                val = zones_glass.get(key)
                lines.append(f"    {label:<30}  r = {_fmt_zone(val)}")
        else:
            lines.append("    Остекление:               —")

        _PEOPLE_LABELS = {
            "people_severe_kPa":   "Люди — тяжёлые (70 кПа)",
            "people_moderate_kPa": "Люди — средние (30 кПа)",
            "people_light_kPa":    "Люди — лёгкие  (12 кПа)",
        }
        zones_people = results.get("zones_people")
        if zones_people:
            for key, label in _PEOPLE_LABELS.items():
                val = zones_people.get(key)
                lines.append(f"    {label:<30}  r = {_fmt_zone(val)}")
        else:
            lines.append("    Люди:                     —")

        zones_buildings = results.get("zones_buildings")
        if zones_buildings:
            for k, v in zones_buildings.items():
                if isinstance(v, (list, tuple)) and len(v) == 2:
                    r_in, r_out = v
                    lines.append(
                        f"    Здания зона {k:<5}  "
                        f"от {_fmt_zone(r_in)}  до {_fmt_zone(r_out)}"
                    )
                else:
                    lines.append(f"    Здания ({k}):  {v}")
        else:
            lines.append("    Здания:                   —")

        prit_r0 = tvs.get("pr4_r0")
        if prit_r0 is not None:
            lines.append(_line("Пробит барабан. перепонок:", prit_r0, decimals=3, unit="(r=0)"))

    lines.append("")
    return lines


def _section_72(jf: dict) -> list[str]:
    lines = []
    lines.append("──── П.7.2. Факельное горение " + "─" * 43)
    lines.append("")

    skip = jf.get("skip_reason")
    if skip:
        lines.append(f"  Пропуск: {skip}")
        lines.append("")
        return lines

    params = jf.get("params") or {}

    lines.append("  Входные параметры:")
    lines.append(_line("Массовый расход ṁ:", params.get("M_kg_s"), decimals=4, unit="кг/с"))
    lines.append("")

    lines.append("  Параметры факела:")
    lines.append(_line("Длина факела LF:", params.get("LF_m"), decimals=2, unit="м"))
    lines.append(_line("Диаметр факела DF:", params.get("DF_m"), decimals=2, unit="м"))
    lines.append(_line("Интенсивность Ef:", params.get("Ef_kw_m2"), decimals=1, unit="кВт/м²"))
    lines.append("")

    lines.append("  Зоны поражения (тепловое излучение):")
    lines.extend(_zone_rows(jf.get("zones")))
    lines.append("")
    return lines


def _section_73(fb: dict) -> list[str]:
    lines = []
    lines.append("──── П.7.3. Огненный шар " + "─" * 47)
    lines.append("")

    skip = fb.get("skip_reason")
    if skip:
        lines.append(f"  Пропуск: {skip}")
        lines.append("")
        return lines

    params = fb.get("params") or {}

    lines.append("  Входные параметры:")
    lines.append(_line("Масса выброса Mг:", params.get("m_kg"), decimals=2, unit="кг"))
    lines.append("")

    lines.append("  Параметры огненного шара:")
    lines.append(_line("Диаметр Ds:", params.get("Ds_m"), decimals=2, unit="м"))
    lines.append(_line("Высота центра H:", params.get("H_m"), decimals=2, unit="м"))
    lines.append(_line("Длительность ts:", params.get("ts_s"), decimals=2, unit="с"))
    lines.append(_line("Интенсивность Ef:", params.get("Ef_kw_m2"), decimals=1, unit="кВт/м²"))
    lines.append("")

    lines.append("  Зоны поражения (тепловое излучение):")
    lines.extend(_zone_rows(fb.get("zones")))
    lines.append("")
    return lines


def build_calculation_debug_output(results: dict) -> str:
    """
    Принимает p.results одного ПОУО.
    Возвращает форматированный текст для вывода в UI.
    """
    lines = []

    # --- Заголовок ---
    meta = results.get("meta") or {}
    code = meta.get("code", "—")
    title = meta.get("title") or meta.get("fuel_title", "—")
    fuel = meta.get("fuel_title", "—")
    space_str = "помещение" if meta.get("is_indoor") else "открытая площадка"

    lines.append("═" * 72)
    lines.append(f"  ПОУО: {code} — {title}")
    lines.append(f"  Топливо: {fuel}  |  {space_str.capitalize()}")
    lines.append("═" * 72)
    lines.append("")

    # --- Ошибка / пропуск ---
    if results.get("error"):
        lines.append(f"  ❌ Ошибка расчёта: {results['error']}")
        return "\n".join(lines)

    if results.get("skip"):
        lines.append(f"  ⚠ Пропуск: {results['skip']}")
        return "\n".join(lines)

    rel = results.get("release") or {}
    tvs = results.get("tvs_explosion") or {}
    jf = results.get("jet_fire") or {}
    fb = results.get("fireball") or {}

    # --- Разделы 7.1 / 7.2 / 7.3 ---
    lines.extend(_section_71(rel, tvs))
    lines.extend(_section_72(jf))
    lines.extend(_section_73(fb))

    return "\n".join(lines)
