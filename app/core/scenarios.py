# app/core/scenarios.py
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Literal

Space = Literal["indoor", "outdoor"]


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    space: Space
    allowed_fuels: List[str]
    # какие поля ввода нужны UI:
    needs_pipes: bool = True
    needs_pressure: bool = True        # P0_kpa
    needs_shutoff: bool = True         # t_shutoff_s
    needs_room_volume: bool = False    # V_room_m3


SCENARIOS: Dict[str, Scenario] = {
    "POUO1": Scenario(
        id="POUO1",
        title="Резервуарный парк (тип топлива, количество и объем каждой емкости)",
        space="outdoor",
        allowed_fuels=["diesel", "lpg"],
        needs_pipes=False,
        needs_pressure=False,
        needs_shutoff=False,
        needs_room_volume=False,
    ),
    "POUO2": Scenario(
        id="POUO2",
        title="Котельная: трубопроводы природного газа высокого давления (узел подключения)",
        space="outdoor",
        allowed_fuels=["natgas"],
        needs_pipes=True,
        needs_pressure=True,
        needs_shutoff=True,
        needs_room_volume=False,
    ),
    "POUO3": Scenario(
        id="POUO3",
        title="Котельная: внутренние трубопроводы природного газа среднего давления",
        space="indoor",
        allowed_fuels=["natgas"],
        needs_pipes=True,
        needs_pressure=True,
        needs_shutoff=True,
        needs_room_volume=True,
    ),
    "POUO4": Scenario(
        id="POUO4",
        title="Котельная: трубопроводы СУГ или другого топлива (в помещении)",
        space="indoor",
        allowed_fuels=["lpg", "diesel"],
        needs_pipes=True,
        needs_pressure=True,
        needs_shutoff=True,
        needs_room_volume=True,
    ),
    "POUO5": Scenario(
        id="POUO5",
        title="Котельная: водонагревательные котлы (в помещении)",
        space="indoor",
        allowed_fuels=["natgas", "lpg", "diesel"],
        needs_pipes=False,
        needs_pressure=False,
        needs_shutoff=False,
        needs_room_volume=True,
    ),
    "POUO6": Scenario(
        id="POUO6",
        title="Испарительная установка с наружными трубопроводами СУГ",
        space="outdoor",
        allowed_fuels=["lpg"],
        needs_pipes=True,
        needs_pressure=True,
        needs_shutoff=True,
        needs_room_volume=False,
    ),
}
