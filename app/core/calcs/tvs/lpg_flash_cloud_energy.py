from __future__ import annotations

import math

from app.core.context import CalculationContext
from app.core.calcs.tank_park.flash_lpg import run_lpg_flash


def _require_positive(ctx: CalculationContext, key: str) -> float:
    try:
        value = float(ctx.intermediate[key])
    except KeyError as exc:
        raise ValueError(f"POUO6: не рассчитан обязательный показатель {key}") from exc
    except (TypeError, ValueError) as exc:
        raise ValueError(f"POUO6: показатель {key} не является числом") from exc

    if value <= 0:
        raise ValueError(f"POUO6: показатель {key} должен быть > 0, получено {value}")
    return value


def _sum_r2l(pipes: list[dict]) -> float:
    return sum(float(p["r_m"]) ** 2 * float(p["L_m"]) for p in pipes)


def _accident_or_first_pipe(pipes: list[dict]) -> dict:
    return next((p for p in pipes if p.get("is_accident")), pipes[0])


def _choked_vapor_rate_kg_s(*, area_m2: float, pressure_pa: float, gamma: float, r0: float, temp_k: float, mu: float) -> float:
    """
    GV: массовый расход паровой фазы через отверстие в критическом режиме.

    GV = μ * A * P * sqrt(gamma / (R0*T) * (2/(gamma+1))^((gamma+1)/(gamma-1)))
    """
    crit = (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (gamma - 1.0))
    return mu * area_m2 * pressure_pa * math.sqrt(gamma / (r0 * temp_k) * crit)


def _run_pouo6_two_phase(ctx: CalculationContext) -> bool:
    """
    Раздел 11 POUO6: две независимые системы СУГ.

    vapor:
      V = 0.01 * pi * P * sum(r^2 * L)
      M_vapor = V * rho_vapor

    liquid:
      GV -> GL
      M_liq = GL * t
      V_gas = M_liq * 0.51
      m_cloud = V_gas * C_st
      M_g = M1T + m_i
      m_tvs = M_g * Z
      E = m_tvs * Q * energy_multiplier

    Для downstream-сценариев:
      Mg_kg = M_total = M_vapor + m_cloud
      m_dot_kg_s = GL
    """
    spec = ctx.inputs.get("lpg_pipe")
    if not spec:
        return False

    liquid = spec["liquid"]
    vapor = spec["vapor"]
    const = spec.get("constants", {})
    subst = ctx.inputs["substance"]
    rel = ctx.inputs["release"]

    liquid_pipes = liquid["pipes"]
    vapor_pipes = vapor["pipes"]
    if not liquid_pipes or not vapor_pipes:
        raise ValueError("POUO6: нужны трубы жидкой и паровой фаз.")
    if sum(1 for pipe in liquid_pipes + vapor_pipes if pipe.get("is_accident")) != 1:
        raise ValueError("POUO6: для расчёта нужен ровно один общий аварийный участок.")

    t_off = float(rel["t_shutoff_s"])
    if t_off <= 0:
        raise ValueError("POUO6: t_shutoff_s должен быть > 0.")

    p_vapor_kpa = float(vapor["P_kPa"])
    p_liquid_pa = float(liquid["P_kPa"]) * 1000.0
    rho_vapor = float(const.get("rho_vapor_kg_m3", 1.8332))
    rho_liq = float(const.get("rho_liq_kg_m3", 520.0))
    vapor_yield = float(const.get("vapor_yield_m3_kg", 0.51))
    c_st = float(const.get("C_st_kg_m3", subst["C_st_kg_m3"]))
    energy_multiplier = float(const.get("energy_multiplier", 2.0))
    p_crit_pa = float(const.get("P_crit_Pa", 4_190_000.0))
    gamma = float(const.get("gamma", 1.257))
    r0 = float(const.get("R0_J_kgK", rel["R0_J_kgK"]))
    temp_k = float(const.get("T_liq_K", rel["T_K"]))
    t_crit = float(const.get("T_crit_K", 370.0))
    if min(p_vapor_kpa, p_liquid_pa, rho_vapor, rho_liq, vapor_yield, c_st, energy_multiplier, p_crit_pa) <= 0:
        raise ValueError("POUO6: фазовые давления и физические константы должны быть > 0.")

    vapor_volume_m3 = 0.01 * math.pi * p_vapor_kpa * _sum_r2l(vapor_pipes)
    vapor_mass_kg = vapor_volume_m3 * rho_vapor

    accident_pipe = _accident_or_first_pipe(liquid_pipes + vapor_pipes)
    area_m2 = math.pi * float(accident_pipe["r_m"]) ** 2
    gv_kg_s = _choked_vapor_rate_kg_s(
        area_m2=area_m2,
        pressure_pa=p_liquid_pa,
        gamma=gamma,
        r0=r0,
        temp_k=temp_k,
        mu=float(rel["psi"]),
    )
    tr = temp_k / t_crit
    pr = p_liquid_pa / p_crit_pa
    if tr <= 0 or pr <= 0:
        raise ValueError("POUO6: TR и PR должны быть > 0 для расчёта GL.")
    # templatePOUO6, раздел 11: GL = GV * sqrt((rhoL/rhoV) * PR) / (1.22 * TR^(3/2)).
    gl_kg_s = gv_kg_s * math.sqrt((rho_liq / rho_vapor) * pr) / (1.22 * (tr ** 1.5))
    liquid_mass_kg = gl_kg_s * t_off
    gas_volume_m3 = liquid_mass_kg * vapor_yield
    cloud_mass_kg = gas_volume_m3 * c_st
    total_mass_kg = vapor_mass_kg + cloud_mass_kg
    tvs_cloud_mass_kg = total_mass_kg * float(ctx.inputs["cloud"]["Z"])
    eud = float(subst["beta"]) * float(subst["Eud0_J_kg"])
    energy_j = tvs_cloud_mass_kg * eud * energy_multiplier

    for key, value in {
        "M_vapor_kg": vapor_mass_kg,
        "M_liquid_kg": liquid_mass_kg,
        "m_cloud_kg": cloud_mass_kg,
        "m_tvs_kg": tvs_cloud_mass_kg,
        "Mg_kg": total_mass_kg,
        "m_dot_kg_s": gl_kg_s,
        "E_J": energy_j,
    }.items():
        if value <= 0:
            raise ValueError(f"POUO6: {key} должен быть > 0, получено {value}")

    ctx.intermediate.update({
        "pouo6_two_phase": True,
        # Обозначения строго по templatePOUO6.docx, раздел 11.
        "V1T_m3": vapor_volume_m3,
        "M1T_kg": vapor_mass_kg,
        "GV_kg_s": gv_kg_s,
        "GL_kg_s": gl_kg_s,
        "PR_liquid": pr,
        "TR_liquid": tr,
        "Mzh_kg": liquid_mass_kg,
        "VGVS_m3": gas_volume_m3,
        "mi_kg": cloud_mass_kg,
        "Mg_total_kg": total_mass_kg,
        "mg_tvs_kg": tvs_cloud_mass_kg,
        "E_template_J": energy_j,
        "vapor_sum_r2L_m3": _sum_r2l(vapor_pipes),
        "vapor_volume_m3": vapor_volume_m3,
        "vapor_mass_kg": vapor_mass_kg,
        "liquid_orifice_area_m2": area_m2,
        "liquid_mass_kg": liquid_mass_kg,
        "liquid_gas_volume_m3": gas_volume_m3,
        "cloud_mass_kg": cloud_mass_kg,
        "tvs_cloud_mass_kg": tvs_cloud_mass_kg,
        "total_mass_kg": total_mass_kg,
        "m_total_kg": total_mass_kg,
        "m_evap_kg": cloud_mass_kg,
        "m_flash_kg": cloud_mass_kg,
        "m_pool_evap_kg": 0.0,
        "m_dot_release_kg_s": gl_kg_s,
        "m_dot_kg_s": gl_kg_s,
        "m_dot_peak_kg_s": gl_kg_s,
        "Mg_kg": total_mass_kg,
        "m_cloud_kg": tvs_cloud_mass_kg,
        "Eud_J_kg": eud,
        "E_concentration_correction": energy_multiplier,
        "E_J": energy_j,
    })

    ctx.log(
        "[pouo6_two_phase] "
        f"M_vapor={vapor_mass_kg:.6g} kg, GL={gl_kg_s:.6g} kg/s, "
        f"M_liq={liquid_mass_kg:.6g} kg, m_cloud={cloud_mass_kg:.6g} kg, "
        f"m_tvs={tvs_cloud_mass_kg:.6g} kg, "
        f"M_total={total_mass_kg:.6g} kg, E={energy_j:.6g} J"
    )
    return True


def run_lpg_flash_cloud_energy(ctx: CalculationContext) -> None:
    """
    Optional POUO6 branch: total LPG pipe release -> flash/pool evaporation
    -> vapor cloud mass and energy.

    The module is intentionally a no-op unless inputs["lpg_flash"] is present,
    so existing TVS recipes keep the original release_cloud_energy result.
    """
    flash = ctx.inputs.get("lpg_flash")
    if not flash:
        return

    if _run_pouo6_two_phase(ctx):
        return

    m_total = _require_positive(ctx, "Mg_kg")

    subst = ctx.inputs["substance"]
    cloud = ctx.inputs["cloud"]

    ctx.intermediate["m_dot_release_kg_s"] = ctx.intermediate.get("m_dot_kg_s")
    ctx.intermediate["m_total_kg"] = m_total

    previous_spill = ctx.inputs.get("spill")
    ctx.inputs["spill"] = {
        "duration_s": flash["duration_s"],
        "flash_fraction": flash.get("flash_fraction", 0.30),
        "pool_evap_fraction": flash.get("pool_evap_fraction", 0.10),
        "peak_duration_s": flash.get("peak_duration_s", 2.5),
    }
    try:
        run_lpg_flash(ctx)
    finally:
        if previous_spill is None:
            ctx.inputs.pop("spill", None)
        else:
            ctx.inputs["spill"] = previous_spill

    m_evap = _require_positive(ctx, "m_evap_kg")
    _require_positive(ctx, "m_dot_kg_s")
    _require_positive(ctx, "m_dot_peak_kg_s")

    m_cloud = m_evap * float(cloud["Z"])
    Eud = float(subst["beta"]) * float(subst["Eud0_J_kg"])
    C_st = float(subst["C_st_kg_m3"])
    C_g = float(subst["C_g_kg_m3"])
    correction = 1.0 if C_g <= C_st else C_st / C_g
    E = m_cloud * Eud * correction

    if m_cloud <= 0:
        raise ValueError(f"POUO6: масса облака m_cloud_kg должна быть > 0, получено {m_cloud}")
    if E <= 0:
        raise ValueError(f"POUO6: энергозапас E_J должен быть > 0, получено {E}")

    ctx.intermediate["m_cloud_kg"] = m_cloud
    ctx.intermediate["Eud_J_kg"] = Eud
    ctx.intermediate["E_concentration_correction"] = correction
    ctx.intermediate["E_J"] = E

    ctx.log(
        "[lpg_flash_cloud_energy] "
        f"m_evap={ctx.intermediate['m_evap_kg']:.6g} kg, "
        f"Z={float(cloud['Z']):.3g}, m_cloud={m_cloud:.6g} kg, E={E:.6g} J"
    )
