from __future__ import annotations

import math
from typing import Dict, Any


def _fq_gost(L: float, d: float, X: float, theta: float = 0.0) -> float:
    """
    Угловой коэффициент облучённости Fq по ГОСТ Р 12.3.047-2012, формулы B.5–B.15.

      Fq = √(Fv² + Fh²)                                               (B.5)

    Параметры:
      L     — длина пламени, м
      d     — эффективный диаметр пламени у основания, м  (B.16: d = √(4F/π))
      X     — горизонтальное расстояние от геометрического центра
               пролива до облучаемого объекта, м
      theta — угол наклона пламени от вертикали (рад), по умолчанию 0

    При theta = 0 (без ветра) формулы существенно упрощаются:
      E = a/b,  C = b,  F·sinθ = 0  → arctan-блок = arctan(a/F)
    """
    if d <= 0 or L <= 0:
        return 0.0

    sin_t = math.sin(theta)
    cos_t = math.cos(theta)

    a = 2.0 * L / d   # B.8: a = 2L/d
    b = 2.0 * X / d   # B.9: b = 2X/d

    # Цель внутри проекции пламени (b < 1) → F и D нереальны;
    # используем минимальный отступ, Fq будет максимальным.
    b = max(b, 1.0 + 1e-6)

    # ── Вспомогательные переменные B.10–B.15 ───────────────────────
    A_val = math.sqrt(max(a**2 + (b + 1)**2 - 2.0*a*(b + 1)*sin_t, 1e-15))  # B.10
    B_val = math.sqrt(max(a**2 + (b - 1)**2 - 2.0*a*(b - 1)*sin_t, 1e-15))  # B.11
    C_val = math.sqrt(max(1.0 + (b**2 - 1.0)*cos_t**2, 1e-15))              # B.12
    D_val = math.sqrt(max((b - 1.0) / (b + 1.0), 0.0))                       # B.13

    denom_E = b - a * sin_t
    E_val = (a * cos_t / denom_E) if abs(denom_E) > 1e-12 else math.copysign(1e9, a * cos_t)  # B.14

    F_val = math.sqrt(max(b**2 - 1.0, 0.0))                                  # B.15

    # ── Общий arctan-блок для косинус/синус-членов ─────────────────
    # При theta=0 и F>0: atan((ab)/(F·b)) + atan(0) = atan(a/F)
    if F_val < 1e-12 or C_val < 1e-12:
        atan_block = 0.0
    else:
        t_a = (a * b - F_val**2 * sin_t) / (F_val * C_val)
        t_b = (F_val**2 * sin_t) / (F_val * C_val)
        atan_block = math.atan(t_a) + math.atan(t_b)

    # arctan(A·D/B) — общий для Fv и Fh
    arctan_AD_B = math.atan(A_val * D_val / B_val) if B_val > 1e-12 else math.pi / 2.0

    # ── B.6 — Fv: фактор облучённости вертикальной площадки ────────
    numer_v = a**2 + (b + 1)**2 - 2.0 * b * (1.0 + a * sin_t)
    Fv = (1.0 / math.pi) * (
        -E_val * math.atan(D_val)
        + E_val * (numer_v / (A_val * B_val)) * arctan_AD_B
        + (cos_t / C_val) * atan_block
    )

    # ── B.7 — Fh: фактор облучённости горизонтальной площадки ─────
    atan_inv_D = (math.atan(1.0 / D_val) if D_val > 1e-12 else math.pi / 2.0)
    numer_h = a**2 + (b + 1)**2 - 2.0 * (b + 1.0 + a * b * sin_t)
    Fh = (1.0 / math.pi) * (
        atan_inv_D
        + (sin_t / C_val) * atan_block
        - (numer_h / (A_val * B_val)) * arctan_AD_B
    )

    # ── B.5 — Fq ───────────────────────────────────────────────────
    Fv = max(Fv, 0.0)
    Fh = max(Fh, 0.0)
    return math.sqrt(Fv**2 + Fh**2)


def calc_jetfire_by_M(
    *,
    M_kg_s: float,
    K: float = 12.5,
    Ef_kw_m2: float = 80.0,
    theta_rad: float = 0.0,
) -> Dict[str, Any]:
    """
    Расчёт факельного горения по ГОСТ Р 12.3.047-2012, Приложение Б.

      LF = K · M^0.4          — длина пламени, м                 (B.17/B.18)
      DF = 0.15 · LF          — эффективный диаметр у основания, м  (B.16)
      H  = LF / 2             — высота центра тяжести пламени, м

    τ(r) — коэффициент пропускания атмосферы:
      dist = max(0, √(r² + H²) − DF/2)  — расстояние от поверхности факела
      τ(r) = exp(−7·10⁻⁴ · dist)

    Fq(r) — угловой коэффициент по ГОСТ Б.5–Б.15 (цилиндрический факел):
      a = 2·LF/DF,  b = 2·r/DF,  Fq = √(Fv² + Fh²)

    q(r) = Ef · Fq · τ  [кВт/м²]

    Зоны поражения: пороги 1.4 / 4.2 / 7.0 / 10.5 кВт/м².

    Параметры:
      theta_rad — угол наклона факела от вертикали (рад); 0 = без ветра
    """
    LF = K * (M_kg_s ** 0.4) if M_kg_s > 0 else 0.0
    DF = 0.15 * LF if LF > 0 else 0.0

    def tau(r: float) -> float:
        # Расстояние от ближайшей точки поверхности факела до цели
        H_c = LF / 2.0
        X_3d = math.sqrt(r * r + H_c * H_c)    # центр → цель
        dist = max(0.0, X_3d - DF / 2.0)       # вычитаем радиус факела
        return math.exp(-7e-4 * dist)

    def fq(r: float) -> float:
        return _fq_gost(L=LF, d=DF, X=r, theta=theta_rad)

    # Таблица расстояний для отчёта/графиков
    r_grid = [0, 1, 2, 3, 5] + list(range(10, 101, 5)) + [125, 150, 200]

    rows = []
    for r in r_grid:
        t = tau(float(r))
        f = fq(float(r))
        q = Ef_kw_m2 * f * t
        rows.append({
            "r_m":     float(r),
            "tau":     float(t),
            "Fq":      float(f),
            "q_kw_m2": float(q),
        })

    thresholds = [1.4, 4.2, 7.0, 10.5]
    zones = []

    for thr in thresholds:
        dist = None
        for i in range(len(rows) - 1):
            r0, q0 = rows[i]["r_m"],     rows[i]["q_kw_m2"]
            r1, q1 = rows[i + 1]["r_m"], rows[i + 1]["q_kw_m2"]

            if abs(q0 - thr) < 1e-9:
                dist = r0
                break

            if (q0 - thr) * (q1 - thr) < 0:
                tlin = (thr - q0) / (q1 - q0)
                dist = r0 + tlin * (r1 - r0)
                break

        zones.append({
            "q_thr_kw_m2": thr,
            "r_m": None if dist is None else round(dist, 1),
        })

    return {
        "params": {
            "M_kg_s":    float(M_kg_s),
            "LF_m":      float(LF),
            "DF_m":      float(DF),
            "Ef_kw_m2":  float(Ef_kw_m2),
            "theta_deg": round(math.degrees(theta_rad), 1),
        },
        "table": rows,
        "zones": zones,
    }
