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


def calc_people_probit(delta_p_pa: float, i_plus_pa_s: float) -> float | None:
    """
    Приближённая probit-оценка поражения человека ударной волной.

    Нужна, чтобы:
    - заполнять таблицу для Word;
    - не ломать шаблон;
    - иметь стабильные численные значения для всех строк.

    Если давления или импульса нет — возвращаем None.
    """
    if delta_p_pa <= 0 or i_plus_pa_s <= 0:
        return None

    val = ((17500.0 / delta_p_pa) ** 8.4) + ((290.0 / i_plus_pa_s) ** 9.3)
    if val <= 0:
        return None

    return 5.0 - 0.26 * math.log(val)


def calc_building_probit(
    delta_p_kpa: float,
    center_kpa: float,
    slope_kpa: float = 5.0,
) -> float | None:
    """
    Простая монотонная probit-модель для таблиц разрушения зданий.

    center_kpa — примерно уровень, где вероятность около 50%.
    slope_kpa  — 'крутизна' перехода.
    """
    if delta_p_kpa <= 0:
        return None
    return 5.0 + (delta_p_kpa - center_kpa) / slope_kpa
