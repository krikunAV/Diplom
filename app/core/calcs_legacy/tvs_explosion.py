# app/core/calcs/tvs_explosion.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Literal
import math
import os

import matplotlib.pyplot as plt


SpaceKind = Literal["type1", "type2", "type3", "type4"]  # 1..4 по методике
FuelClass = Literal[1, 2, 3, 4]
ExplosionRange = Literal[1, 2, 3, 4, 5, 6]


@dataclass
class TVSExplosionResult:
    params: Dict[str, float]
    table_rows: List[Dict[str, float]]
    chart_dp_path: Optional[str] = None
    chart_imp_path: Optional[str] = None


# ----------------------- helpers -----------------------

def _safe_ln(x: float) -> float:
    return math.log(max(x, 1e-12))


def _choose_vg(range_id: ExplosionRange, m_g_kg: float) -> float:
    """
    Выбор скорости фронта пламени Vg (м/с).
    В шаблоне обычно берут среднее по диапазону.
    Для 5/6: Vg = k * M^(1/6)
    """
    if range_id == 1:
        return 500.0  # детонация/>=500
    if range_id == 2:
        return 400.0
    if range_id == 3:
        return 250.0
    if range_id == 4:
        return 175.0
    if range_id == 5:
        return 43.0 * (m_g_kg ** (1.0 / 6.0))
    if range_id == 6:
        return 26.0 * (m_g_kg ** (1.0 / 6.0))
    return 250.0


def _detonation_px_ix(Rx: float) -> Tuple[float, float]:
    """
    Детонационная ветка (Px2, Ix2) по шаблону.
    Ограничения:
      - Px2: если Rx < 0.2 => Px2 = 18
      - Ix2: если Rx < 0.2 => подставляем Rx = 0.14
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
    Дефлаграционная ветка (Px1, Ix1) по шаблону.
    Ограничение: если Rx < 0.34, подставляем Rx=0.34.
    """
    Rx_eff = max(Rx, 0.34)

    ksig = (sigma - 1.0) / sigma
    a = (Vg / C0)

    # Px1 = (Vg/C0)^2 * ((σ-1)/σ) * (0.83/Rx - 0.14/Rx^2)
    Px1 = (a ** 2) * ksig * (0.83 / Rx_eff - 0.14 / (Rx_eff ** 2))

    # Ix1 = (Vg/C0) * ((σ-1)/σ) * (1 - 0.4(σ-1)Vg/(σC0)) * (0.06/Rx + 0.01/Rx^2 - 0.0025/Rx^3)
    corr = 1.0 - 0.4 * (sigma - 1.0) * Vg / (sigma * C0)
    Ix1 = a * ksig * corr * (0.06 / Rx_eff + 0.01 / (Rx_eff ** 2) - 0.0025 / (Rx_eff ** 3))

    # защита от отрицательных чисел (в реальности там физически не должно уходить в минус)
    Px1 = max(Px1, 0.0)
    Ix1 = max(Ix1, 0.0)
    return Px1, Ix1


def _build_r_grid(max_r: float = 200.0) -> List[float]:
    """
    Сетка расстояний близкая к шаблону:
    0,1,2,3,5,10,15,20,...,100,125,150,200 (и дальше если нужно)
    """
    r = [0, 1, 2, 3, 5]
    r += list(range(10, 101, 5))
    r += [125, 150, 200]
    r = [float(x) for x in r if x <= max_r]
    if r[-1] < max_r:
        r.append(float(max_r))
    return sorted(set(r))


def _ensure_dir(path: str) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)


def _plot_series(x: List[float], y: List[float], title: str, xlabel: str, ylabel: str, out_path: str) -> str:
    _ensure_dir(out_path)
    plt.figure()
    plt.plot(x, y)
    plt.title(title)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=180)
    plt.close()
    return out_path


# ----------------------- main calc -----------------------

def calc_tvs_explosion(
    *,
    m_g_kg: float,                 # масса горючего в облаке, участвующая во взрыве
    q_g_j_per_kg: float,           # теплота сгорания, Дж/кг
    c_g: float,                    # средняя концентрация в смеси (об.)
    c_st: float,                   # стехиометрическая концентрация (об.)
    fuel_class: FuelClass,         # класс вещества 1..4
    space_kind: SpaceKind,         # вид окружающего пространства type1..type4
    range_id: ExplosionRange,      # диапазон режима 1..6 (если хочешь — потом сделаем авто-выбор по таблице)
    sigma: float,                  # 7 для газовых, 4 для гетерогенных
    p0_pa: float = 101325.0,
    c0_m_s: float = 340.0,
    max_r_m: float = 200.0,
    make_charts: bool = True,
    chart_dp_path: str = "out/charts/tvs_dp.png",
    chart_imp_path: str = "out/charts/tvs_imp.png",
) -> TVSExplosionResult:
    """
    Возвращает структуру строго под отчёт:
      - params: E, Vg и т.п.
      - table_rows: список строк r,Rx,Px1,Ix1,Px2,Ix2,Px,Ix,deltaP_Pa,Iplus_Pa_s
      - графики (опционально)
    """

    if m_g_kg <= 0:
        raise ValueError("m_g_kg must be > 0")
    if q_g_j_per_kg <= 0:
        raise ValueError("q_g_j_per_kg must be > 0")

    # Эффективный энергозапас E
    if c_g <= c_st:
        E = m_g_kg * q_g_j_per_kg
    else:
        E = m_g_kg * q_g_j_per_kg * (c_st / max(c_g, 1e-12))

    # скорость фронта
    Vg = _choose_vg(range_id, m_g_kg)

    # масштаб длины (E/P0)^(1/3)
    L_scale = (E / p0_pa) ** (1.0 / 3.0)

    # таблица по расстояниям
    r_grid = _build_r_grid(max_r_m)

    rows: List[Dict[str, float]] = []

    dp_series = []
    imp_series = []
    x_series = []

    for r in r_grid:
        Rx = 0.0 if r == 0 else (r / L_scale)

        # детонация
        Px2, Ix2 = _detonation_px_ix(Rx if Rx > 0 else 1e-12)

        # дефлаграция
        Px1, Ix1 = _deflagration_px_ix(Rx if Rx > 0 else 1e-12, Vg, c0_m_s, sigma)

        Px = min(Px1, Px2)
        Ix = min(Ix1, Ix2)

        deltaP = Px * p0_pa
        Iplus = Ix * ((p0_pa ** (2.0 / 3.0)) * (E ** (1.0 / 3.0)) / c0_m_s)

        rows.append({
            "r_m": float(r),
            "Rx": float(Rx),
            "Px1": float(Px1),
            "Ix1": float(Ix1),
            "Px2": float(Px2),
            "Ix2": float(Ix2),
            "Px": float(Px),
            "Ix": float(Ix),
            "deltaP_Pa": float(deltaP),
            "Iplus_Pa_s": float(Iplus),
        })

        x_series.append(float(r))
        dp_series.append(float(deltaP))
        imp_series.append(float(Iplus))

    dp_path = None
    imp_path = None
    if make_charts:
        dp_path = _plot_series(
            x_series, dp_series,
            title="Избыточное давление ΔP(r)",
            xlabel="r, м",
            ylabel="ΔP, Па",
            out_path=chart_dp_path,
        )
        imp_path = _plot_series(
            x_series, imp_series,
            title="Импульс положительной фазы I+(r)",
            xlabel="r, м",
            ylabel="I+, Па·с",
            out_path=chart_imp_path,
        )

    params = {
        "m_g_kg": float(m_g_kg),
        "q_g_j_per_kg": float(q_g_j_per_kg),
        "c_g": float(c_g),
        "c_st": float(c_st),
        "E_J": float(E),
        "Vg_m_s": float(Vg),
        "p0_pa": float(p0_pa),
        "c0_m_s": float(c0_m_s),
        "sigma": float(sigma),
        "L_scale_m": float(L_scale),
        "fuel_class": float(fuel_class),
        "space_kind": float(int(space_kind.replace("type", ""))),
        "range_id": float(range_id),
        "max_r_m": float(max_r_m),
    }

    return TVSExplosionResult(
        params=params,
        table_rows=rows,
        chart_dp_path=dp_path,
        chart_imp_path=imp_path,
    )