# app/core/calcs/tvs/release_cloud_energy.py
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.core.context import CalculationContext


@dataclass
class ReleaseCloudEnergyResult:
    # Блок 1 (7.1): ключевые промежуточные/итоговые величины
    F_m2: float
    v_g_m3_kg: float
    m_dot_kg_s: float
    M1T_kg: float
    sum_r2L_m3: float
    V2T_m3: float
    M2T_kg: float
    Mg_kg: float
    m_cloud_kg: float
    Eud_J_kg: float
    E_J: float
    E_concentration_correction: Optional[float] = None


def _sum_r2L(pipes: List[Dict[str, Any]]) -> float:
    s = 0.0
    for p in pipes:
        r = float(p["r_m"])
        L = float(p["L_m"])
        if r <= 0 or L <= 0:
            raise ValueError("Each pipe must have r_m > 0 and L_m > 0")
        s += (r ** 2) * L
    return s


def run_release_cloud_energy(ctx: CalculationContext) -> ReleaseCloudEnergyResult:
    """
    Block 1 (7.1): Выброс -> облако ТВС -> энергозапас (E)

    Формулы (как ты задала):
      F = pi*d^2/4
      v_g = R0*T/Pg
      m_dot = psi*F*mu*sqrt(Pg/v_g)
      M1T = m_dot * t_shutoff
      V2T = 0.01*pi*P2(kPa)*sum(r^2*L)
      M2T = V2T * rho
      Mg = M1T + M2T
      m_cloud = Mg * Z
      Eud = beta * Eud0
      if Cg <= Cst: E = m_cloud * Eud
      else:         E = m_cloud * Eud * (Cst/Cg)

    Требует inputs по CONTEXT_SPEC:
      inputs.release, inputs.isolated_section, inputs.substance, inputs.cloud
    Пишет:
      ctx.intermediate: F_m2, v_g_m3_kg, m_dot_kg_s, M1T_kg, sum_r2L_m3, V2T_m3, M2T_kg,
                        Mg_kg, m_cloud_kg, Eud_J_kg, E_J, E_concentration_correction(optional)
    """

    inp = ctx.inputs
    subst = inp["substance"]
    rel = inp["release"]
    iso = inp["isolated_section"]
    cloud = inp["cloud"]

    # --- Inputs ---
    d = float(rel["orifice_d_m"])
    mu = float(rel["mu"])
    psi = float(rel["psi"])
    Pg = float(rel["Pg_Pa"])
    T = float(rel["T_K"])
    R0 = float(rel["R0_J_kgK"])
    t_off = float(rel["t_shutoff_s"])

    P2_kPa = float(iso["P2_kPa"])
    pipes = iso["pipes"]

    rho = float(subst["rho_gas_kg_m3"])
    Eud0 = float(subst["Eud0_J_kg"])
    beta = float(subst["beta"])

    # концентрации (обязательные в твоём правиле)
    C_st = float(subst["C_st_kg_m3"])
    C_g = float(subst["C_g_kg_m3"])

    Z = float(cloud["Z"])

    # --- Basic sanity checks ---
    if d <= 0:
        raise ValueError("orifice_d_m must be > 0")
    if Pg <= 0:
        raise ValueError("Pg_Pa must be > 0")
    if T <= 0:
        raise ValueError("T_K must be > 0")
    if R0 <= 0:
        raise ValueError("R0_J_kgK must be > 0")
    if t_off <= 0:
        raise ValueError("t_shutoff_s must be > 0")
    if rho <= 0:
        raise ValueError("rho_gas_kg_m3 must be > 0")
    if Eud0 <= 0:
        raise ValueError("Eud0_J_kg must be > 0")
    if not (0 <= Z <= 1):
        raise ValueError("Z must be in [0, 1]")
    if C_st <= 0 or C_g <= 0:
        raise ValueError("C_st_kg_m3 and C_g_kg_m3 must be > 0")

    # --- 7.1 formulas ---
    F = math.pi * (d ** 2) / 4.0
    v_g = (R0 * T) / Pg  # m^3/kg

    if v_g <= 0:
        raise ValueError("Computed v_g_m3_kg <= 0; check R0, T_K, Pg_Pa")

    m_dot = psi * F * mu * math.sqrt(Pg / v_g)
    M1T = m_dot * t_off

    s_r2L = _sum_r2L(pipes)

    # В методике 7.1: P2 в кПа, множитель 0.01*pi*P2*sum(r^2 L)
    V2T = 0.01 * math.pi * P2_kPa * s_r2L

    M2T = V2T * rho
    Mg = M1T + M2T

    m_cloud = Mg * Z

    Eud = beta * Eud0

    if C_g <= C_st:
        correction = 1.0
        E = m_cloud * Eud
    else:
        correction = C_st / C_g
        E = m_cloud * Eud * correction

    # --- Save intermediate for reproducibility ---
    ctx.intermediate["F_m2"] = F
    ctx.intermediate["v_g_m3_kg"] = v_g
    ctx.intermediate["m_dot_kg_s"] = m_dot
    ctx.intermediate["M1T_kg"] = M1T
    ctx.intermediate["sum_r2L_m3"] = s_r2L
    ctx.intermediate["V2T_m3"] = V2T
    ctx.intermediate["M2T_kg"] = M2T
    ctx.intermediate["Mg_kg"] = Mg
    ctx.intermediate["m_cloud_kg"] = m_cloud
    ctx.intermediate["Eud_J_kg"] = Eud
    ctx.intermediate["E_concentration_correction"] = correction
    ctx.intermediate["E_J"] = E

    ctx.log(f"[7.1] F={F:.6g} m2, v_g={v_g:.6g} m3/kg, m_dot={m_dot:.6g} kg/s")
    ctx.log(f"[7.1] M1T={M1T:.6g} kg, V2T={V2T:.6g} m3, M2T={M2T:.6g} kg, Mg={Mg:.6g} kg")
    ctx.log(f"[7.1] m_cloud={m_cloud:.6g} kg, Eud={Eud:.6g} J/kg, correction={correction:.6g}, E={E:.6g} J")

    return ReleaseCloudEnergyResult(
        F_m2=F,
        v_g_m3_kg=v_g,
        m_dot_kg_s=m_dot,
        M1T_kg=M1T,
        sum_r2L_m3=s_r2L,
        V2T_m3=V2T,
        M2T_kg=M2T,
        Mg_kg=Mg,
        m_cloud_kg=m_cloud,
        Eud_J_kg=Eud,
        E_J=E,
        E_concentration_correction=correction,
    )