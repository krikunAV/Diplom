# app/domain/registry.py
from __future__ import annotations

from typing import Dict

from app.domain.base import BaseScenario
from app.domain.tvs_explosion import TVSExplosionScenario
from app.domain.jet_fire import JetFireScenario
from app.domain.fireball import FireballScenario
from app.domain.tank_park import TankParkScenario
from app.domain.indoor_natgas import IndoorNatgasScenario, JetFireStubScenario
from app.domain.indoor_lpg import IndoorLpgScenario, LpgJetFireStubScenario

SCENARIO_REGISTRY: Dict[str, BaseScenario] = {
    "tvs_explosion": TVSExplosionScenario(),
    "jet_fire": JetFireScenario(),
    "fireball": FireballScenario(),
    "tank_park": TankParkScenario(),
    "indoor_natgas": IndoorNatgasScenario(),
    "indoor_lpg": IndoorLpgScenario(),
    "jet_fire_stub": JetFireStubScenario(),
    "lpg_jet_fire_stub": LpgJetFireStubScenario(),
}


def get_scenario(scenario_type: str) -> BaseScenario:
    """
    Возвращает экземпляр сценария по типу.
    Бросает KeyError если тип неизвестен.
    """
    if scenario_type not in SCENARIO_REGISTRY:
        available = list(SCENARIO_REGISTRY)
        raise KeyError(
            f"Неизвестный тип сценария: {scenario_type!r}. "
            f"Доступные: {available}"
        )
    return SCENARIO_REGISTRY[scenario_type]
