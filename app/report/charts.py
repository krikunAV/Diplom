# app/report/charts.py
"""Построение графиков по готовым результатам pipeline (после engine.compute_for_pouo)."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("Agg")  # без оконного GUI
import matplotlib.pyplot as plt


# ─────────────────────────────────────────────────────────
# Вспомогательные
# ─────────────────────────────────────────────────────────

def _save_fig(fig: "plt.Figure", path: str) -> None:
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _line_ax(
    ax: "plt.Axes",
    x: List[float],
    y: List[float],
    xlabel: str,
    ylabel: str,
    title: str,
    color: str = "#1f77b4",
) -> None:
    ax.plot(x, y, color=color, linewidth=1.8, marker="o", markersize=3)
    ax.set_xlabel(xlabel, fontsize=10)
    ax.set_ylabel(ylabel, fontsize=10)
    ax.set_title(title, fontsize=10)
    ax.grid(True, alpha=0.3)


# ─────────────────────────────────────────────────────────
# График 1: ΔP(r)
# ─────────────────────────────────────────────────────────

def save_tvs_dp_chart(
    results: Dict[str, Any],
    output_dir: str,
    pouo_code: str,
) -> Optional[str]:
    """
    Сохраняет график избыточного давления ΔP(r).

    Источник данных: results["tvs_explosion"]["results"]["r_grid_m"] и ["dP_Pa"].
    Возвращает путь к PNG или None, если данных нет.
    """
    tvs = (results or {}).get("tvs_explosion") or {}
    if tvs.get("skip_reason"):
        return None

    res = tvs.get("results") or {}
    r: List[float] = res.get("r_grid_m") or []
    dp_pa: List[float] = res.get("dP_Pa") or []

    if len(r) < 2 or len(dp_pa) != len(r):
        return None

    dp_kpa = [v / 1000.0 for v in dp_pa]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    _line_ax(ax, r, dp_kpa, "r, м", "ΔP, кПа", f"ΔP(r) — {pouo_code}")

    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"tvs_dp_{pouo_code}.png")
    _save_fig(fig, path)
    return path


# ─────────────────────────────────────────────────────────
# График 2: I+(r)
# ─────────────────────────────────────────────────────────

def save_tvs_impulse_chart(
    results: Dict[str, Any],
    output_dir: str,
    pouo_code: str,
) -> Optional[str]:
    """
    Сохраняет график импульса положительной фазы I+(r).

    Источник данных: results["tvs_explosion"]["results"]["r_grid_m"] и ["Iplus_Pa_s"].
    Возвращает путь к PNG или None, если данных нет.
    """
    tvs = (results or {}).get("tvs_explosion") or {}
    if tvs.get("skip_reason"):
        return None

    res = tvs.get("results") or {}
    r: List[float] = res.get("r_grid_m") or []
    ip: List[float] = res.get("Iplus_Pa_s") or []

    if len(r) < 2 or len(ip) != len(r):
        return None

    fig, ax = plt.subplots(figsize=(8, 4.5))
    _line_ax(ax, r, ip, "r, м", "I+, Па·с", f"I+(r) — {pouo_code}", color="#d62728")

    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"tvs_imp_{pouo_code}.png")
    _save_fig(fig, path)
    return path


# ─────────────────────────────────────────────────────────
# График 3: q(r) — факельное горение
# ─────────────────────────────────────────────────────────

def save_jetfire_chart(
    results: Dict[str, Any],
    output_dir: str,
    pouo_code: str,
) -> Optional[str]:
    """
    Сохраняет график теплового излучения q(r) факельного горения.

    Источник данных: results["jet_fire"]["table"] — поля r_m и q_kw_m2.
    Возвращает путь к PNG или None, если данных нет.
    """
    jf = (results or {}).get("jet_fire") or {}
    if jf.get("skip_reason"):
        return None

    rows = jf.get("table") or []
    r_j: List[float] = []
    q_j: List[float] = []
    for row in rows:
        try:
            r_j.append(float(row["r_m"]))
            q_j.append(float(row["q_kw_m2"]))
        except (KeyError, TypeError, ValueError):
            continue

    if len(r_j) < 2:
        return None

    fig, ax = plt.subplots(figsize=(8, 4.5))
    _line_ax(ax, r_j, q_j, "r, м", "q, кВт/м²", f"Jet fire q(r) — {pouo_code}", color="#ff7f0e")

    # Горизонтальные пороговые линии (нормативные уровни поражения)
    for thr, label in [(1.4, "1.4"), (4.2, "4.2"), (7.0, "7.0"), (10.5, "10.5")]:
        ax.axhline(thr, linestyle="--", linewidth=0.8, color="#888", alpha=0.7)
        ax.text(r_j[-1], thr + 0.1, f"{label} кВт/м²", fontsize=8, color="#555", ha="right")

    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"jetfire_{pouo_code}.png")
    _save_fig(fig, path)
    return path


# ─────────────────────────────────────────────────────────
# Общая точка входа
# ─────────────────────────────────────────────────────────

def write_pouo_charts(
    results: Dict[str, Any],
    output_dir: str,
    pouo_code: str,
) -> Dict[str, Optional[str]]:
    """
    Строит все три графика для одного ПОУО и возвращает словарь путей.

    Вызывается после engine.compute_for_pouo, получает POUO.results.
    Не меняет pipeline, не пересчитывает физику.

    Пример возвращаемого значения::

        {
            "tvs_dp":  "out/charts/tvs_dp_POUO2.png",
            "tvs_imp": "out/charts/tvs_imp_POUO2.png",
            "jetfire": "out/charts/jetfire_POUO2.png",
        }

    Если график не удалось построить — соответствующее значение None.
    """
    return {
        "tvs_dp":  save_tvs_dp_chart(results, output_dir, pouo_code),
        "tvs_imp": save_tvs_impulse_chart(results, output_dir, pouo_code),
        "jetfire": save_jetfire_chart(results, output_dir, pouo_code),
    }
