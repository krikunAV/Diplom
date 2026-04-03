from __future__ import annotations

import math


def probit_to_percent(pr: float | None) -> float | None:
    """
    Перевод probit -> вероятность в %.
    В классической probit-модели значение 5 соответствует примерно 50%.
    """
    if pr is None:
        return None

    z = pr - 5.0
    p = 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))
    return max(0.0, min(100.0, p * 100.0))


def calc_people_probit(
    delta_p_pa: float,
    i_plus_pa_s: float,
    p0_pa: float = 101325.0,
    mass_kg: float = 70.0,
) -> float | None:
    """
    Pr3 — вероятность нокдауна/тяжёлых травм человека от ударной волны.

    Приказ Ростехнадзора № 412 (2022), ГОСТ Р 12.3.047:
      Pr3 = 5 − 5.74 × ln(V3)
      V3  = 4.2/p̄ + 1.3/Ī
      p̄  = 1 + ΔP/P0
      Ī   = I / (P0^(1/2) × m^(1/3))

    Параметры:
      delta_p_pa  — избыточное давление, Па
      i_plus_pa_s — импульс фазы сжатия, Па·с
      p0_pa       — атмосферное давление, Па (по умолчанию 101325)
      mass_kg     — масса тела человека, кг (по умолчанию 70)

    Возвращает None при некорректных или вырожденных входных данных.
    """
    if delta_p_pa <= 0 or i_plus_pa_s <= 0:
        return None

    p_bar = 1.0 + delta_p_pa / p0_pa
    i_bar = i_plus_pa_s / (p0_pa ** 0.5 * mass_kg ** (1.0 / 3.0))

    if i_bar <= 0:
        return None

    V3 = 4.2 / p_bar + 1.3 / i_bar

    # Численная устойчивость: при экстремально больших ΔP и I оба слагаемых
    # стремятся к 0, ln(V3) → -inf. Возвращаем None — «вне области модели».
    if V3 <= 1e-12:
        return None

    return 5.0 - 5.74 * math.log(V3)


def calc_building_probit_pr1(
    delta_p_pa: float,
    i_plus_pa_s: float,
) -> float | None:
    """
    Pr1 — вероятность повреждений зданий (восстановимые разрушения).

    Приказ Ростехнадзора № 412 (2022):
      Pr1 = 5 − 0.26 × ln(V1)
      V1  = (17500/ΔP)^8.4 + (290/I)^9.3

    Параметры:
      delta_p_pa  — избыточное давление, Па
      i_plus_pa_s — импульс фазы сжатия, Па·с

    Возвращает None при некорректных или вырожденных входных данных.
    """
    if delta_p_pa <= 0 or i_plus_pa_s <= 0:
        return None

    V1 = (17500.0 / delta_p_pa) ** 8.4 + (290.0 / i_plus_pa_s) ** 9.3

    # При экстремально больших ΔP и I оба члена → 0, V1 → 0, ln → -inf.
    if V1 <= 1e-12:
        return None

    return 5.0 - 0.26 * math.log(V1)


def calc_building_probit_pr2(
    delta_p_pa: float,
    i_plus_pa_s: float,
) -> float | None:
    """
    Pr2 — вероятность полного разрушения зданий (снос).

    Приказ Ростехнадзора № 412 (2022):
      Pr2 = 5 − 0.22 × ln(V2)
      V2  = (40000/ΔP)^7.4 + (460/I)^11.3

    Параметры:
      delta_p_pa  — избыточное давление, Па
      i_plus_pa_s — импульс фазы сжатия, Па·с

    Возвращает None при некорректных или вырожденных входных данных.
    """
    if delta_p_pa <= 0 or i_plus_pa_s <= 0:
        return None

    V2 = (40000.0 / delta_p_pa) ** 7.4 + (460.0 / i_plus_pa_s) ** 11.3

    # При экстремально больших ΔP и I оба члена → 0, V2 → 0, ln → -inf.
    if V2 <= 1e-12:
        return None

    return 5.0 - 0.22 * math.log(V2)
