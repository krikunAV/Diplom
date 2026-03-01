# app/core/context_spec.py
from __future__ import annotations

# Спецификация структуры CalculationContext для сценария 7.1 (без ущерба/жертв)
# Вложенная структура inputs: inputs["release"]["Pg_Pa"] и т.п.

CONTEXT_SPEC = {
    "inputs": {
        "meta": {
            "scenario_id": {"type": "str", "required": True},
            "calc_date": {"type": "str", "required": False},
            "notes": {"type": "str", "required": False},
        },
        "env": {
            "P0_Pa": {"type": "number", "required": True},
            "C0_mps": {"type": "number", "required": True},
            "wind_mps": {"type": "number", "required": True},
        },
        "substance": {
            "rho_gas_kg_m3": {"type": "number", "required": True},
            "Eud0_J_kg": {"type": "number", "required": True},
            "beta": {"type": "number", "required": True},
            "sigma": {"type": "number", "required": True},
            # Если считаешь Cст и/или Cг по формулам в модуле — можно не требовать
            "C_st_kg_m3": {"type": "number", "required": False},
            "C_g_kg_m3": {"type": "number", "required": False},
        },
        "release": {
            "orifice_d_m": {"type": "number", "required": True},
            "mu": {"type": "number", "required": True},
            "psi": {"type": "number", "required": True},
            "Pg_Pa": {"type": "number", "required": True},
            "T_K": {"type": "number", "required": True},
            "R0_J_kgK": {"type": "number", "required": True},
            "t_shutoff_s": {"type": "number", "required": True},
        },
        "isolated_section": {
            "P2_kPa": {"type": "number", "required": True},
            "pipes": {
                "type": "list",
                "required": True,
                "items": {
                    "r_m": {"type": "number", "required": True},
                    "L_m": {"type": "number", "required": True},
                },
            },
        },
        "cloud": {
            "Z": {"type": "number", "required": True},
            "cloud_model": {"type": "str", "required": True},  # "open_area" | "indoor"
        },
        "shockwave": {
            "r_grid_m": {"type": "list", "required": True, "items_type": "number"},
            "explosion_mode": {"type": "str", "required": True},  # "detonation" | "deflagration"
        },
    },

    # Поля intermediate/results не валидируем как обязательные ДО расчёта.
    # Но оставляем перечень "ожидаемых" для отчёта/валидации (после выполнения модулей).
    "expected_intermediate_after_calc": [
        "F_m2", "v_g_m3_kg", "m_dot_kg_s", "M1T_kg",
        "sum_r2L_m3", "V2T_m3", "M2T_kg", "Mg_kg",
        "m_cloud_kg", "Eud_J_kg", "E_J"
    ],
    "expected_results_after_calc": [
        "dP_Pa", "Iplus_Pa_s",
        "zones_buildings", "zones_glass", "zones_people"
    ],
}