# app/core/calcs/tvs/shockwave.py
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any

from app.core.context import CalculationContext


def _safe_ln(x: float) -> float:
    """
    Безопасный натуральный логарифм.

    В расчётах ударной волны встречается ln(Rx).
    Для r = 0 приведённое расстояние Rx тоже стремится к 0,
    поэтому защищаемся от log(0) и log(отрицательного).
    """
    return math.log(max(x, 1e-12))


def _detonation_px_ix(Rx: float) -> Tuple[float, float]:
    """
    Безразмерные давление Px и импульс Ix для детонационного режима.

    Формулы:
      если Rx < 0.2:
          Px = 18
          для Ix вместо Rx берём 0.14
      иначе:
          ln(Px) = -1.124 - 1.66 ln(Rx) + 0.26 ln(Rx)^2
          ln(Ix) = -3.4217 - 0.898 ln(Rx) - 0.0096 ln(Rx)^2
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
    Безразмерные давление Px и импульс Ix для дефлаграционного режима.

    Здесь используется ограничение:
      Rx_eff = max(Rx, 0.34)

    Это соответствует методике, когда выражение справедливо
    только начиная с критического приведённого расстояния.
    """
    Rx_eff = max(Rx, 0.34)

    # ksig = (σ - 1) / σ
    ksig = (sigma - 1.0) / sigma

    # a = Vg / C0 — отношение скорости фронта пламени к скорости звука
    a = Vg / C0

    Px1 = (a ** 2) * ksig * (0.83 / Rx_eff - 0.14 / (Rx_eff ** 2))

    corr = 1.0 - 0.4 * (sigma - 1.0) * Vg / (sigma * C0)
    Ix1 = a * ksig * corr * (
        0.06 / Rx_eff +
        0.01 / (Rx_eff ** 2) -
        0.0025 / (Rx_eff ** 3)
    )

    # На всякий случай не даём уйти в отрицательные значения
    Px1 = max(Px1, 0.0)
    Ix1 = max(Ix1, 0.0)

    return Px1, Ix1


def _choose_vg(range_id: int, m_cloud_kg: float) -> float:
    """
    Выбор скорости фронта пламени Vg по диапазону режима сгорания.

    range_id = 1..6

    Для диапазонов 5 и 6 скорость зависит от массы облака:
      range 5: Vg = 43 * M^(1/6)
      range 6: Vg = 26 * M^(1/6)
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

    # Запасной вариант
    return 250.0


@dataclass
class ShockwaveResult:
    """
    Возвращаемый результат блока ударной волны.

    Эти же данные параллельно сохраняются в ctx.intermediate и ctx.results,
    чтобы downstream-блоки и engine.py могли их использовать без пересчёта.
    """
    r_grid_m: List[float]
    Rx: List[float]
    Px: List[float]
    Ix: List[float]
    dP_Pa: List[float]
    Iplus_Pa_s: List[float]
    params: Dict[str, Any]


def run_shockwave(ctx: CalculationContext) -> ShockwaveResult:
    """
    Block 2: расчёт параметров ударной волны.

    Что берём:
      - env.P0_Pa
      - env.C0_mps
      - substance.sigma
      - shockwave.explosion_mode
      - shockwave.r_grid_m
      - shockwave.range_id
      - intermediate.E_J
      - intermediate.m_cloud_kg

    Что считаем:
      - приведённое расстояние Rx
      - безразмерные Px и Ix
      - реальное избыточное давление dP_Pa
      - импульс фазы сжатия Iplus_Pa_s

    Что сохраняем:
      - intermediate["L_scale_m"], ["Rx"], ["Px"], ["Ix"]
      - results["r_grid_m"], ["dP_Pa"], ["Iplus_Pa_s"], ["shockwave_params"]
    """
    inp = ctx.inputs
    env = inp["env"]
    subst = inp["substance"]
    sh = inp["shockwave"]

    # Атмосферные и средовые параметры
    P0 = float(env["P0_Pa"])
    C0 = float(env["C0_mps"])
    sigma = float(subst["sigma"])

    # Режим: detonation / deflagration
    mode = sh["explosion_mode"]

    # Сетка расстояний, на которых считаем волну
    r_grid = [float(x) for x in sh["r_grid_m"]]

    # Энергозапас должен быть рассчитан предыдущим блоком
    E = float(ctx.intermediate["E_J"])
    if E <= 0:
        raise ValueError("E_J must be > 0")

    # Масштаб длины по методике
    L_scale = (E / P0) ** (1.0 / 3.0)

    # Для дефлаграции нужна скорость фронта пламени
    range_id = int(sh.get("range_id", 3))
    m_cloud = float(ctx.intermediate.get("m_cloud_kg", 0.0))

    if mode == "deflagration":
        Vg = _choose_vg(range_id, m_cloud)
    else:
        Vg = None

    # Массивы результата
    Rx_list: List[float] = []
    Px_list: List[float] = []
    Ix_list: List[float] = []
    dP_list: List[float] = []
    Iplus_list: List[float] = []

    for r in r_grid:
        # Для r=0 используем очень маленькое значение,
        # чтобы не делить на ноль и не брать log(0)
        Rx = (r / L_scale) if r > 0 else 1e-12

        if mode == "detonation":
            Px, Ix = _detonation_px_ix(Rx)
        else:
            Px, Ix = _deflagration_px_ix(Rx, float(Vg), C0, sigma)

        # Перевод безразмерных величин в физические
        dP = Px * P0
        Iplus = Ix * ((P0 ** (2.0 / 3.0)) * (E ** (1.0 / 3.0)) / C0)

        Rx_list.append(float(Rx))
        Px_list.append(float(Px))
        Ix_list.append(float(Ix))
        dP_list.append(float(dP))
        Iplus_list.append(float(Iplus))

    # ---------------- Сохраняем промежуточные данные ----------------
    ctx.intermediate["L_scale_m"] = float(L_scale)
    ctx.intermediate["Rx"] = Rx_list
    ctx.intermediate["Px"] = Px_list
    ctx.intermediate["Ix"] = Ix_list

    # ---------------- Сохраняем основные результаты ----------------
    ctx.results["r_grid_m"] = r_grid
    ctx.results["dP_Pa"] = dP_list
    ctx.results["Iplus_Pa_s"] = Iplus_list

    # Это критично для engine.py:
    # теперь engine может взять готовые параметры без ручного пересчёта
    ctx.results["shockwave_params"] = {
        "mode": mode,
        "range_id": range_id if mode == "deflagration" else None,
        "Vg_m_s": float(Vg) if Vg is not None else None,
        "P0_Pa": P0,
        "C0_mps": C0,
        "sigma": sigma,
        "E_J": E,
        "L_scale_m": float(L_scale),
    }

    ctx.log(
        f"[shockwave] mode={mode}, "
        f"E={E:.6g}, "
        f"L_scale={L_scale:.6g}, "
        f"Vg={float(Vg) if Vg is not None else 'n/a'}"
    )

    return ShockwaveResult(
        r_grid_m=r_grid,
        Rx=Rx_list,
        Px=Px_list,
        Ix=Ix_list,
        dP_Pa=dP_list,
        Iplus_Pa_s=Iplus_list,
        params=ctx.results["shockwave_params"],
    )