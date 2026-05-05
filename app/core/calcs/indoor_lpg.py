from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List

from app.core.context import CalculationContext


@dataclass
class IndoorLpgResult:
    F_m2: float
    v_g_m3_kg: float
    m_dot_kg_s: float
    M1T_kg: float
    V1T_m3: float
    V2T_m3: float
    M2T_kg: float
    Mg_kg: float
    m_cloud_kg: float
    deltaP_kPa: float


def _sum_r2L(pipes: List[Dict[str, Any]]) -> float:
    total = 0.0
    for pipe in pipes:
        r = float(pipe["r_m"])
        L = float(pipe["L_m"])
        if r <= 0 or L <= 0:
            raise ValueError("POUO4: каждый участок должен иметь r_m > 0 и L_m > 0.")
        total += r * r * L
    return total


def gas_release(ctx: CalculationContext) -> None:
    """
    POUO4, 9.1: секундный массовый расход паровой фазы СУГ.

      F = pi*d^2/4
      Vg = R0*T/Pg
      M = psi*F*mu*sqrt(Pg/Vg)
    """
    rel = ctx.inputs["release"]

    d = float(rel["orifice_d_m"])
    mu = float(rel["mu"])
    psi = float(rel["psi"])
    Pg = float(rel["Pg_Pa"])
    T = float(rel["T_K"])
    R0 = float(rel["R0_J_kgK"])

    if d <= 0:
        raise ValueError("POUO4: orifice_d_m должен быть > 0.")
    if Pg <= 0:
        raise ValueError("POUO4: Pg_Pa должен быть > 0.")
    if T <= 0 or R0 <= 0:
        raise ValueError("POUO4: T_K и R0_J_kgK должны быть > 0.")
    if mu <= 0 or psi <= 0:
        raise ValueError("POUO4: mu и psi должны быть > 0.")

    F = math.pi * d * d / 4.0
    v_g = R0 * T / Pg
    m_dot = psi * F * mu * math.sqrt(Pg / v_g)

    ctx.intermediate.update({
        "F_m2": F,
        "v_g_m3_kg": v_g,
        "m_dot_kg_s": m_dot,
        "M_kg_s": m_dot,
    })
    ctx.log(f"[POUO4 gas_release] F={F:.6g} m2, Vg={v_g:.6g} m3/kg, M={m_dot:.6g} kg/s")


def mass_calculation(ctx: CalculationContext) -> None:
    """
    POUO4, 9.1: масса СУГ до и после отсечки.

      M1T = M*T
      V2T = 0.01*pi*P2*sum(r_i^2*L_i)
      M2T = V2T*rho_pipe
      Mg = M1T + M2T
      m_cloud = Mg*Z
    """
    rel = ctx.inputs["release"]
    iso = ctx.inputs["isolated_section"]
    subst = ctx.inputs["substance"]
    cloud = ctx.inputs["cloud"]

    m_dot = float(ctx.intermediate["m_dot_kg_s"])
    t_off = float(rel["t_shutoff_s"])
    P2_kPa = float(iso["P2_kPa"])
    rho_pipe = float(subst.get("rho_pipe_kg_m3", subst["rho_gas_kg_m3"]))
    Z = float(cloud["Z"])

    if t_off <= 0:
        raise ValueError("POUO4: t_shutoff_s должен быть > 0.")
    if P2_kPa <= 0:
        raise ValueError("POUO4: P2_kPa должен быть > 0.")
    if rho_pipe <= 0:
        raise ValueError("POUO4: rho_pipe_kg_m3 должен быть > 0.")
    if not 0 <= Z <= 1:
        raise ValueError("POUO4: Z должен быть в диапазоне [0, 1].")

    sum_r2L = _sum_r2L(iso["pipes"])
    M1T = m_dot * t_off
    V1T = math.pi * sum_r2L
    V2T = 0.01 * math.pi * P2_kPa * sum_r2L
    M2T = V2T * rho_pipe
    Mg = M1T + M2T
    m_cloud = Mg * Z

    ctx.intermediate.update({
        "sum_r2L_m3": sum_r2L,
        "M1T_kg": M1T,
        "V1T_m3": V1T,
        "V2T_m3": V2T,
        "M2T_kg": M2T,
        "Mg_kg": Mg,
        "m_cloud_kg": m_cloud,
        "rho_pipe_kg_m3": rho_pipe,
    })
    ctx.log(
        "[POUO4 mass] "
        f"M1T={M1T:.6g} kg, V2T={V2T:.6g} m3, M2T={M2T:.6g} kg, Mg={Mg:.6g} kg"
    )


def explosion_indoor(ctx: CalculationContext) -> IndoorLpgResult:
    """
    POUO4, 9.1: избыточное давление взрыва СУГ в помещении.

      dP = (Pmax - P0) * (m_cloud/(Vfree*rho_gas)) * (100/Cst) * (1/Kn)

    m_cloud уже содержит коэффициент Z, поэтому повторное умножение на Z
    здесь не выполняется.
    """
    room = ctx.inputs["room"]
    subst = ctx.inputs["substance"]

    V_free = float(room["V_free_m3"])
    Pmax = float(room["Pmax_kPa"])
    P0 = float(room["P0_kPa"])
    Kn = float(room["Kn"])
    Cst_percent = float(room["C_st_percent"])

    rho = float(subst["rho_gas_kg_m3"])
    Mg = float(ctx.intermediate["Mg_kg"])
    m_cloud = float(ctx.intermediate["m_cloud_kg"])

    if V_free <= 0:
        raise ValueError("POUO4: V_free_m3 должен быть > 0.")
    if Pmax <= P0:
        raise ValueError("POUO4: Pmax_kPa должен быть больше P0_kPa.")
    if Kn <= 0 or Cst_percent <= 0:
        raise ValueError("POUO4: Kn и C_st_percent должны быть > 0.")
    if rho <= 0:
        raise ValueError("POUO4: rho_gas_kg_m3 должен быть > 0.")

    deltaP_kPa = (Pmax - P0) * (m_cloud / (V_free * rho)) * (100.0 / Cst_percent) / Kn

    ctx.results.update({
        "Mg_kg": Mg,
        "mass_total_kg": Mg,
        "m_cloud_kg": m_cloud,
        "mass_cloud_kg": m_cloud,
        "deltaP_kPa": deltaP_kPa,
        "delta_p": deltaP_kPa,
        "deltaP_Pa": deltaP_kPa * 1000.0,
        "Pmax_kPa": Pmax,
        "P0_kPa": P0,
        "Kn": Kn,
        "C_st_percent": Cst_percent,
        "V_free_m3": V_free,
        "Vsv_m3": V_free,
        "rho_gas_kg_m3": rho,
    })
    ctx.log(f"[POUO4 indoor] dP={deltaP_kPa:.6g} kPa")

    return IndoorLpgResult(
        F_m2=float(ctx.intermediate["F_m2"]),
        v_g_m3_kg=float(ctx.intermediate["v_g_m3_kg"]),
        m_dot_kg_s=float(ctx.intermediate["m_dot_kg_s"]),
        M1T_kg=float(ctx.intermediate["M1T_kg"]),
        V1T_m3=float(ctx.intermediate["V1T_m3"]),
        V2T_m3=float(ctx.intermediate["V2T_m3"]),
        M2T_kg=float(ctx.intermediate["M2T_kg"]),
        Mg_kg=Mg,
        m_cloud_kg=m_cloud,
        deltaP_kPa=deltaP_kPa,
    )


def jet_fire_stub(ctx: CalculationContext) -> None:
    """POUO4, 9.3: факельное горение фиксируется как нерассчитываемое по шаблону."""
    reason = ctx.inputs.get(
        "skip_reason",
        "Расчёт факельного горения для POUO4 не выполняется из-за малой длительности процесса до срабатывания отсечки.",
    )
    ctx.results["skipped"] = True
    ctx.results["reason"] = reason
    ctx.results["skip_reason"] = reason
    ctx.results["m_dot_kg_s"] = float(ctx.inputs.get("m_dot_kg_s", 0.0) or 0.0)
    ctx.results["duration_s"] = float(ctx.inputs.get("duration_s", 0.0) or 0.0)
    ctx.log(f"[POUO4 jet_fire_stub] {reason}")
