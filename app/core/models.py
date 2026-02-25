# app/core/models.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class PipeRow:
    name: str
    length_m: float
    diameter_mm: float
    pressure_kpa: float = 0.0        # если 0 — берём из inputs["P0_kpa"]
    is_accident: bool = False        # ✅ аварийный участок


@dataclass
class POUO:
    code: str
    title: str
    is_indoor: bool
    fuel_id: str                     # natgas / lpg / diesel (или алиасы)
    inputs: Dict[str, Any] = field(default_factory=dict)
    pipes: List[PipeRow] = field(default_factory=list)
    results: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Project:
    name: str
    object_name: str
    address: str
    pouos: List[POUO] = field(default_factory=list)
