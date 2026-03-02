from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple, Literal, Dict, Any

from app.core.context import CalculationContext

ExplosionMode = Literal["detonation", "deflagration"]


def _safe_ln(x: float) -> float:
    return math.log(max(x, 1e-12))


def _detonation_px_ix(Rx: float) -> Tuple[float, float]:
    """
    Детонационная ветка (Px2, Ix2) по методике (шаблон 412).
    Ограничения:
      - Px2: если Rx < 0.2 => Px2 = 18
      - Ix2: если Rx < 0.2 => для Ix используем Rx = 0.14
    """
    if Rx < 0.2:
        Px2 = 18.0
        Rx_for_I = 0.14
    else:
        Rx_for_I = Rx
        lnRx = _safe_ln(Rx)
        lnPx = -1.124 - 1.66 * lnRx + 0.26 * (lnRx ** 2)
        Px2 = math.exp(lnPx)

    lnRxI = _safe_ln(Rx_for_I)
    lnIx = -3.4217 - 0.898 * lnRxI - 0.0096 * (lnRxI ** 2)
    Ix2 = math.exp(lnIx)
    return Px2, Ix2


def _deflagration_px_ix(Rx: float, Vg: float, C0: float, sigma: float) -> Tuple[float, float]:
    """
    Дефлаграционная ветка (Px1, Ix1) по методике (шаблон 412).
    Ограничение: если Rx < 0.34, подставляем Rx=0.34.
    """
    Rx_eff = max(Rx, 0.34)

    ksig = (sigma - 1.0) / sigma
    a = (Vg / C0)

    Px1 = (a ** 2) * ksig * (0.83 / Rx_eff - 0.14 / (Rx_eff ** 2))
    corr = 1.0 - 0.4 * (sigma - 1.0) * Vg / (sigma * C0)
    Ix1 = a * ksig * corr * (0.06 / Rx_eff + 0.01 / (Rx_eff ** 2) - 0.0025 / (Rx_eff ** 3))

    Px1 = max(Px1, 0.0)
    Ix1 = max(Ix1, 0.0)
    return Px1, Ix1


def _choose_vg(range_id: int, m_cloud_kg: float) -> float:
    """
    Скорость фронта пламени Vg (м/с) по диапазону 1..6.
    Для 5/6: Vg = k * M^(1/6).
    """
    if range_id == 1:
        return 500.0
    if range_id == 2:
        return 400.0
    if range_id == 3:
        return 250.0
    if range_id == 4:
        return 175.0
    if range_id == 5:
        return 43.0 * (m_cloud_kg ** (1.0 / 6.0))
    if range_id == 6:
        return 26.0 * (m_cloud_kg ** (1.0 / 6.0))
    return 250.0


@dataclass
class Shockwave412Result:
    r_grid_m: List[float]
    Rx: List[float]
    Px: List[float]
    Ix: List[float]
    dP_Pa: List[float]
    Iplus_Pa_s: List[float]
    params: Dict[str, Any]


def run_shockwave(ctx: CalculationContext) -> Shockwave412Result:
    """
    Block 2 (412): E -> Rx -> Px/Ix -> ΔP/I+
    Требует:

      ctx.intermediate["E_J"]
      ctx.intermediate["m_cloud_kg"] (для выбора Vg при дефлаграции)
    Использует:
      inputs.env.P0_Pa, inputs.env.C0_mps, inputs.substance.sigma
      inputs.shockwave.r_grid_m, inputs.shockwave.explosion_mode
    Опционально:
      inputs.shockwave.range_id (1..6) — для дефлаграции
    """

    inp = ctx.inputs
    env = inp["env"]
    subst = inp["substance"]
    sh = inp["shockwave"]

    P0 = float(env["P0_Pa"])
    C0 = float(env["C0_mps"])
    sigma = float(subst["sigma"])

    mode: ExplosionMode = sh["explosion_mode"]
    r_grid = [float(x) for x in sh["r_grid_m"]]

    E = float(ctx.intermediate["E_J"])
    if E <= 0:
        raise ValueError("E_J must be > 0 (check Block 1)")

    # масштаб длины (E/P0)^(1/3)
    L_scale = (E / P0) ** (1.0 / 3.0)

    # если дефлаграция — нужен Vg
    range_id = int(sh.get("range_id", 3))  # по умолчанию 3
    m_cloud = float(ctx.intermediate.get("m_cloud_kg", 0.0))
    Vg = _choose_vg(range_id, m_cloud) if mode == "deflagration" else None

    Rx_list: List[float] = []
    Px_list: List[float] = []
    Ix_list: List[float] = []
    dP_list: List[float] = []
    Iplus_list: List[float] = []

    for r in r_grid:
        # Rx = r / L_scale (для r=0 подставим маленькое число)
        Rx = (r / L_scale) if r > 0 else 1e-12

        if mode == "detonation":
            Px, Ix = _detonation_px_ix(Rx)
        else:
            # дефлаграция
            Px, Ix = _deflagration_px_ix(Rx, float(Vg), C0, sigma)

        dP = Px * P0
        Iplus = Ix * ((P0 ** (2.0 / 3.0)) * (E ** (1.0 / 3.0)) / C0)

        Rx_list.append(float(Rx))
        Px_list.append(float(Px))
        Ix_list.append(float(Ix))
        dP_list.append(float(dP))
        Iplus_list.append(float(Iplus))

    # записываем в контекст (воспроизводимость)
    ctx.intermediate["L_scale_m"] = float(L_scale)
    ctx.intermediate["Rx"] = Rx_list
    ctx.intermediate["Px"] = Px_list
    ctx.intermediate["Ix"] = Ix_list

    ctx.results["r_grid_m"] = r_grid
    ctx.results["dP_Pa"] = dP_list
    ctx.results["Iplus_Pa_s"] = Iplus_list

    # параметры расчёта
    params = {
        "mode": mode,
        "range_id": range_id if mode == "deflagration" else None,
        "Vg_m_s": float(Vg) if Vg is not None else None,
        "P0_Pa": P0,
        "C0_mps": C0,
        "sigma": sigma,
        "E_J": E,
        "L_scale_m": float(L_scale),
    }

    ctx.log(f"[412] mode={mode}, E={E:.6g} J, L_scale={L_scale:.6g} m")

    return Shockwave412Result(
        r_grid_m=r_grid,
        Rx=Rx_list,
        Px=Px_list,
        Ix=Ix_list,
        dP_Pa=dP_list,
        Iplus_Pa_s=Iplus_list,
        params=params,
    )