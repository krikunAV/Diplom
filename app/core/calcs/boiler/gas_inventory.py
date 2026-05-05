# app/core/calcs/boiler/gas_inventory.py
"""
Расчёт массы газа (инвентарь при аварии) для POUO10 — котельная.

V_a — объём газа, покинувшего аппарат при аварии, м³ (не геометрия котла и не объём воды).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

ConfigLike = Union[Mapping[str, Any], Any]


def _cfg_get(config: ConfigLike, key: str, default: Any = None) -> Any:
    if isinstance(config, Mapping):
        return config.get(key, default)
    return getattr(config, key, default)


def _resolve_fuel_rho_kg_m3(fuel: str, config: ConfigLike) -> float:
    fuel = fuel.lower().strip()
    if fuel not in ("natgas", "lpg"):
        raise ValueError(f"fuel must be 'natgas' or 'lpg', got {fuel!r}")

    presets = _cfg_get(config, "fuel_presets")
    if isinstance(presets, Mapping) and fuel in presets:
        row = presets[fuel]
        if isinstance(row, Mapping) and row.get("rho_kg_m3") is not None:
            return float(row["rho_kg_m3"])

    if fuel == "natgas":
        v = _cfg_get(config, "rho_natgas_kg_m3")
        if v is not None:
            return float(v)
        v = _cfg_get(config, "rho_natgas_n")
        if v is not None:
            return float(v)
    else:
        v = _cfg_get(config, "rho_lpg_kg_m3")
        if v is not None:
            return float(v)
        v = _cfg_get(config, "indoor_lpg_rho_pipe_kg_m3")
        if v is not None:
            return float(v)

    raise ValueError(
        f"Не задана плотность для {fuel!r}: укажите fuel_presets[{fuel!r}][rho_kg_m3] "
        "или поле конфигурации rho_natgas_n / indoor_lpg_rho_pipe_kg_m3 (EngineConfig)."
    )


def _boiler_presets_map(config: ConfigLike) -> Mapping[str, Any]:
    bp = _cfg_get(config, "boiler_presets")
    if bp is None:
        bp = _cfg_get(config, "boiler_models")
    if bp is None:
        return {}
    if not isinstance(bp, Mapping):
        raise TypeError("boiler_presets должен быть отображением model -> параметры.")
    return bp


def _resolve_V_a_m3(boiler_row: Mapping[str, Any], config: ConfigLike) -> float:
    if boiler_row.get("V_a_m3") is not None:
        v = float(boiler_row["V_a_m3"])
        if v < 0:
            raise ValueError("V_a_m3 не может быть отрицательным.")
        return v
    model = str(boiler_row.get("model", "")).strip()
    if not model:
        raise ValueError("В записи котла должен быть указан model или V_a_m3.")
    presets = _boiler_presets_map(config)
    if model not in presets:
        raise KeyError(
            f"Нет V_a_m3 в записи и нет пресета boiler_presets[{model!r}]. "
            "Передайте V_a_m3 в boilers или добавьте пресет."
        )
    entry = presets[model]
    if not isinstance(entry, Mapping):
        raise TypeError(f"Пресет котла {model!r} должен быть словарём с V_a_m3.")
    if entry.get("V_a_m3") is None:
        raise KeyError(f"В пресете {model!r} отсутствует V_a_m3.")
    v = float(entry["V_a_m3"])
    if v < 0:
        raise ValueError(f"V_a_m3 в пресете {model!r} не может быть отрицательным.")
    return v


def calc_apparatus_release_mass(
    boilers: Sequence[Mapping[str, Any]],
    fuel: str,
    config: ConfigLike,
) -> Dict[str, Any]:
    """
    m_a = Σ(count × V_a × ρ_топлива)

    V_a, м³ — объём аварийного выброса из аппарата (паспорт / методика), не геометрия.
    """
    rho = _resolve_fuel_rho_kg_m3(fuel, config)
    by_boiler: List[Dict[str, Any]] = []
    mass_total_kg = 0.0

    for row in boilers:
        count = int(row["count"])
        if count <= 0:
            raise ValueError("count каждого котла должен быть > 0.")
        model = str(row.get("model", "")).strip()
        if not model:
            raise ValueError("У каждого котла должен быть непустой model.")
        V_a = _resolve_V_a_m3(row, config)
        mass_kg = count * V_a * rho
        mass_total_kg += mass_kg
        by_boiler.append(
            {
                "model": model,
                "count": count,
                "V_a_m3": V_a,
                "rho_kg_m3": rho,
                "mass_kg": mass_kg,
            }
        )

    return {"by_boiler": by_boiler, "mass_total_kg": mass_total_kg}


def _t_off_s(config: ConfigLike) -> float:
    t = _cfg_get(config, "t_off_s")
    if t is not None:
        return float(t)
    t = _cfg_get(config, "t_shutoff_s")
    if t is not None:
        return float(t)
    rel = _cfg_get(config, "release")
    if isinstance(rel, Mapping) and rel.get("t_shutoff_s") is not None:
        return float(rel["t_shutoff_s"])
    raise ValueError("Задайте t_off_s (или t_shutoff_s / release.t_shutoff_s).")


def calc_pipe_release_before_isolation(config: ConfigLike) -> Dict[str, Any]:
    """
    Масса газа до отсечки:

      m_1T = G × t_off

    G — секундный массовый расход, кг/с; t_off — время до отсечки, с.
    """
    warnings: List[str] = []
    G_raw = _cfg_get(config, "G_kg_s")
    if G_raw is None:
        G_raw = _cfg_get(config, "M_kg_s")
    t_off = _t_off_s(config)

    if G_raw is None:
        warnings.append(
            "TODO: G_kg_s не задан — масса до отсечки m_1T принята 0; "
            "нужен секундный расход для полного расчёта."
        )
        return {
            "mass_kg": 0.0,
            "G_kg_s": None,
            "t_off_s": t_off,
            "warnings": warnings,
        }

    G_kg_s_used = float(G_raw)
    return {
        "mass_kg": G_kg_s_used * t_off,
        "G_kg_s": G_kg_s_used,
        "t_off_s": t_off,
        "warnings": warnings,
    }


def _pipe_radius_m(pipe: Mapping[str, Any]) -> float:
    if pipe.get("r_m") is not None:
        return float(pipe["r_m"])
    d_mm = pipe.get("diameter_mm")
    if d_mm is None:
        d_mm = pipe.get("d_mm")
    if d_mm is not None:
        return float(d_mm) / 1000.0 / 2.0
    raise ValueError("Участок трубы: задайте r_m или diameter_mm.")


def _pipe_length_m(pipe: Mapping[str, Any]) -> float:
    for key in ("l_m", "L_m", "length_m"):
        if pipe.get(key) is not None:
            return float(pipe[key])
    raise ValueError("Участок трубы: задайте l_m или length_m (или L_m).")


def _collect_pipes(config: ConfigLike) -> List[Mapping[str, Any]]:
    if isinstance(config, Mapping):
        pipes = config.get("pipes")
        if pipes is None:
            iso = config.get("isolated_section") or {}
            if isinstance(iso, Mapping):
                pipes = iso.get("pipes")
        if pipes is None:
            pp = config.get("pipe_presets")
            if isinstance(pp, Mapping) and isinstance(pp.get("segments"), list):
                pipes = pp["segments"]
        if pipes is None:
            pipes = []
        return list(pipes)
    pipes = _cfg_get(config, "pipes")
    if pipes is None:
        return []
    return list(pipes)


def _pressure_kpa_for_V2T(config: ConfigLike) -> Optional[float]:
    p = _cfg_get(config, "pressure_kpa")
    if p is not None:
        return float(p)
    p_mpa = _cfg_get(config, "pressure_mpa")
    if p_mpa is not None:
        return float(p_mpa) * 1000.0
    if isinstance(config, Mapping):
        iso = config.get("isolated_section") or {}
        if isinstance(iso, Mapping) and iso.get("P2_kPa") is not None:
            return float(iso["P2_kPa"])
    iso = _cfg_get(config, "isolated_section")
    if isinstance(iso, Mapping) and iso.get("P2_kPa") is not None:
        return float(iso["P2_kPa"])
    return None


def calc_pipe_release_after_isolation(config: ConfigLike, fuel: str) -> Dict[str, Any]:
    """
    Остаточный объём и масса в изолированном участке после отсечки.

      V_2T = 0.01 × π × P × Σ(r_i² × l_i)   [м³]
      m_2T = ρ_топлива × V_2T               [кг]

    Здесь:
    - r_i — внутренний радиус трубы, м;
    - l_i — длина участка, м;
    - P — давление **P₂** в той же размерности, что и в POUO3/POUO4: величина в **кПа**
      подставляется в V2T = 0.01·π·P·Σ(r²·l) (см. `indoor_natgas.mass_calculation`).
      Коэффициент 0.01 принят шаблоном методики; r и l — в метрах.

    pressure_mpa во входе приводится к кПа: P_kPa = P_MPa × 1000.
    """
    rho = _resolve_fuel_rho_kg_m3(fuel, config)
    pipes = _collect_pipes(config)
    warnings: List[str] = []

    sum_r2l = 0.0
    for p in pipes:
        r = _pipe_radius_m(p)
        L = _pipe_length_m(p)
        if r <= 0 or L <= 0:
            raise ValueError("Для каждого участка нужны r_m > 0 (или diameter_mm) и l_m > 0.")
        sum_r2l += r * r * L

    P_kpa_opt = _pressure_kpa_for_V2T(config)
    P_kpa_used: Optional[float]

    if not pipes:
        V_2T = 0.0
        P_kpa_used = None
        warnings.append("Нет участков трубопровода — V_2T = 0.")
    elif P_kpa_opt is None:
        warnings.append(
            "TODO: не задано давление (pressure_kpa / pressure_mpa / isolated_section.P2_kPa) — "
            "V_2T принят 0."
        )
        V_2T = 0.0
        P_kpa_used = None
    else:
        P_kpa = float(P_kpa_opt)
        if P_kpa <= 0:
            raise ValueError("Давление P для расчёта V_2T должно быть > 0 (кПа).")
        # V_2T [м³] = 0.01 * π * P [кПа] * Σ(r²*l) [м⁵] — см. indoor_natgas.mass_calculation
        V_2T = 0.01 * math.pi * P_kpa * sum_r2l
        P_kpa_used = P_kpa

    m_2T = rho * V_2T

    return {
        "residual_volume_m3": V_2T,
        "mass_kg": m_2T,
        "rho_kg_m3": rho,
        "P_kPa_used": P_kpa_used,
        "sum_r2l_m5": sum_r2l,
        "warnings": warnings,
    }


def calc_total_release(
    boilers: Sequence[Mapping[str, Any]],
    fuel: str,
    config: ConfigLike,
) -> Dict[str, Any]:
    """
    m_total = m_a + m_1T + m_2T

    Сводная структура для интеграции с отчётом POUO10.
    """
    app = calc_apparatus_release_mass(boilers, fuel, config)
    pre = calc_pipe_release_before_isolation(config)
    post = calc_pipe_release_after_isolation(config, fuel)

    m_a = float(app["mass_total_kg"])
    m_1T = float(pre["mass_kg"])
    m_2T = float(post["mass_kg"])
    m_total = m_a + m_1T + m_2T

    top_warnings: List[str] = list(pre.get("warnings") or [])
    top_warnings.extend(post.get("warnings") or [])

    result: Dict[str, Any] = {
        "apparatus": {
            "by_boiler": app["by_boiler"],
            "mass_total_kg": m_a,
        },
        "pipe": {
            "mass_pre_isolation_kg": m_1T,
            "mass_post_isolation_kg": m_2T,
            "residual_volume_m3": float(post["residual_volume_m3"]),
        },
        "total": {
            "mass_total_kg": m_total,
        },
        "release": {
            "mass_apparatus_kg": m_a,
            "mass_pipe_pre_isolation_kg": m_1T,
            "mass_pipe_post_isolation_kg": m_2T,
            "mass_total_kg": m_total,
        },
    }
    if top_warnings:
        result["warnings"] = top_warnings
    return result
