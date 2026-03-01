# context_spec.py — ожидаемые ключи в CalculationContext

CONTEXT_SPEC = {
  "inputs": {
    "meta": {
      "scenario_id": "str",
      "calc_date": "str|datetime (optional)",
      "notes": "str (optional)"
    },

    "env": {
      "P0_Pa": "float",
      "C0_mps": "float",
      "wind_mps": "float"
    },

    "substance": {
      "rho_gas_kg_m3": "float",
      "Eud0_J_kg": "float",
      "beta": "float",
      "sigma": "float",
      "C_st_kg_m3": "float (optional if computed)",
      "C_g_kg_m3": "float (optional)"
    },

    "release": {
      "orifice_d_m": "float",
      "mu": "float",
      "psi": "float",
      "Pg_Pa": "float",
      "T_K": "float",
      "R0_J_kgK": "float",
      "t_shutoff_s": "float"
    },

    "isolated_section": {
      "P2_kPa": "float",
      "pipes": [
        {"r_m": "float", "L_m": "float"}
      ]
    },

    "cloud": {
      "Z": "float",
      "cloud_model": "str ('open_area'|'indoor')",
    },

    "shockwave": {
      "r_grid_m": "list[float]",
      "explosion_mode": "str ('detonation'|'deflagration')"
    }
  },

  "intermediate": {
    # Block 1
    "F_m2": "float",
    "v_g_m3_kg": "float",
    "m_dot_kg_s": "float",
    "M1T_kg": "float",
    "sum_r2L_m3": "float",
    "V2T_m3": "float",
    "M2T_kg": "float",
    "Mg_kg": "float",
    "m_cloud_kg": "float",
    "Eud_J_kg": "float",
    "E_J": "float",
    "L_m": "float (optional)",
    "r0_m": "float (optional)",

    # Block 2 (dimensionless)
    "Rx": "list[float]",
    "Px": "list[float]",
    "Ix": "list[float]"
  },

  "results": {
    # Block 2 (dimensional)
    "dP_Pa": "list[float]",
    "Iplus_Pa_s": "list[float]",

    # Block 3
    "probit_people": "list[float] (optional)",
    "prob_people": "list[float] (optional)",
    "zones_buildings": "dict[str, float] (optional)",
    "zones_glass": "dict[str, float] (optional)",
    "zones_people": "dict[str, float] (optional)",

    # For report
    "tables": "dict[str, Any] (optional)",
    "plots": "dict[str, Any] (optional)"
  },

  "validation": {
    "validation_cases": "list[dict] (optional)",
    "validation_summary": "str (optional)",
    "validation_details": "list[dict] (optional)"
  }
}