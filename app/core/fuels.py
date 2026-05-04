# app/core/fuels.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fuel:
    id: str
    title: str
    # Низшая теплота сгорания (если понадобится в 7.1/эквиваленте), Дж/кг
    eud0_j_per_kg: float = 0.0
    # Типовая плотность жидкой фазы (для дизеля/СУГ жидк), кг/м3
    rho_liq: float = 0.0


FUELS: dict[str, Fuel] = {
    "natgas": Fuel(id="natgas", title="Природный газ", eud0_j_per_kg=5.0e7, rho_liq=0.0),
    "lpg": Fuel(id="lpg", title="СУГ (пропан-бутан)", eud0_j_per_kg=4.6e7, rho_liq=520.0),
    # POUO1-DT uses the constants fixed in templatePOUO1_DT.docx and
    # docs/methodology/METHODOLOGY_POUO1_DT.md.
    # ENGINEER_CHECK: rho=860 kg/m3 should be replaced by passport data
    # for the actual diesel grade when available.
    "diesel": Fuel(id="diesel", title="Дизельное топливо", eud0_j_per_kg=43.59e6, rho_liq=860.0),
}

ALIASES: dict[str, str] = {
    "methane": "natgas",
    "metan": "natgas",
    "natural_gas": "natgas",
    "ng": "natgas",
    "gas": "natgas",
    "природный газ": "natgas",

    "sug": "lpg",
    "суг": "lpg",
    "propane_butane": "lpg",
    "propan_butan": "lpg",

    "diesel_fuel": "diesel",
    "дизель": "diesel",
    "дизтопливо": "diesel",
}


def normalize_fuel_id(fuel_id: str) -> str:
    fid = (fuel_id or "").strip().lower()
    return ALIASES.get(fid, fid)


def get_fuel(fuel_id: str) -> Fuel:
    fid = normalize_fuel_id(fuel_id)
    if fid not in FUELS:
        raise KeyError(f"Неизвестное топливо: {fuel_id} (нормализовано как {fid})")
    return FUELS[fid]
