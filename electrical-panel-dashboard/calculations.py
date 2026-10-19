"""
calculations.py — Pure electrical engineering math functions.

All functions are stateless with no Streamlit or Pandas dependencies so they
can be unit-tested in isolation.  Every function documents its formula,
argument units, return units, assumptions, and an "Interview Note" that
explains the underlying engineering concept.

Assumption (applies to all functions unless noted):
    Sinusoidal steady-state at 60 Hz — no harmonic distortion is modeled.
"""

import math

# ---------------------------------------------------------------------------
# Apparent Power
# ---------------------------------------------------------------------------

def apparent_power(V: float, I: float) -> float:
    """
    Calculate apparent power.

    Formula:  S = V × I

    Args:
        V: RMS voltage in volts (V).  Must be >= 0.
        I: RMS current in amps (A).  Must be >= 0.

    Returns:
        Apparent power S in volt-amperes (VA).

    Raises:
        ValueError: If V or I is negative.

    Interview Note:
        Apparent power is the vector magnitude of the power triangle.  It is
        what the utility source "sees" and must supply regardless of load type.
        Generators and transformers are rated in VA (or kVA/MVA) because they
        must handle both the real and reactive components of current.
    """
    if V < 0:
        raise ValueError(f"Voltage must be >= 0, got {V}")
    if I < 0:
        raise ValueError(f"Current must be >= 0, got {I}")
    return V * I


# ---------------------------------------------------------------------------
# Real Power
# ---------------------------------------------------------------------------

def real_power(V: float, I: float, pf: float) -> float:
    """
    Calculate real (active) power.

    Formula:  P = V × I × PF

    Args:
        V:  RMS voltage in volts (V).  Must be >= 0.
        I:  RMS current in amps (A).  Must be >= 0.
        pf: Displacement power factor, dimensionless [0, 1].

    Returns:
        Real power P in watts (W).

    Raises:
        ValueError: If V or I is negative, or pf is outside [0, 1].

    Interview Note:
        Real power is the only component that does useful work — producing
        heat, mechanical torque, or light.  PF = cos(θ) where θ is the phase
        angle between the voltage and current waveforms.  A motor running at
        PF = 0.85 converts only 85 % of apparent power into useful work; the
        remaining 15 % circulates as reactive power.
    """
    if V < 0:
        raise ValueError(f"Voltage must be >= 0, got {V}")
    if I < 0:
        raise ValueError(f"Current must be >= 0, got {I}")
    if not (0.0 <= pf <= 1.0):
        raise ValueError(f"Power factor must be in [0, 1], got {pf}")
    return V * I * pf


# ---------------------------------------------------------------------------
# Reactive Power
# ---------------------------------------------------------------------------

def reactive_power(P: float, S: float) -> float:
    """
    Calculate reactive power from real and apparent power.

    Formula:  Q = sqrt(S² − P²)

    Args:
        P: Real power in watts (W).       Must be >= 0 and <= S.
        S: Apparent power in VA.          Must be >= 0.

    Returns:
        Reactive power Q in volt-amperes reactive (VAR).

    Raises:
        ValueError: If P < 0, S < 0, or S < P (physically impossible).

    Interview Note:
        Reactive power represents energy that oscillates between the source
        and the magnetic/electric fields of inductive/capacitive loads.  It
        does no net work per cycle but does cause real I²R losses in conductors
        and transformers.  Capacitor banks are installed in industrial plants
        to supply reactive power locally, reducing current draw from the grid
        and improving power factor.  The power triangle identity is:
        P² + Q² = S²  (analogous to the Pythagorean theorem).
    """
    if P < 0:
        raise ValueError(f"Real power P must be >= 0, got {P}")
    if S < 0:
        raise ValueError(f"Apparent power S must be >= 0, got {S}")
    if S < P:
        raise ValueError(
            f"Apparent power S ({S}) must be >= real power P ({P}); "
            "S < P is physically impossible."
        )
    if S == P:          # PF = 1.0 → purely resistive load, Q = 0
        return 0.0
    return math.sqrt(S ** 2 - P ** 2)


# ---------------------------------------------------------------------------
# Power Factor from Phase Angle
# ---------------------------------------------------------------------------

def power_factor_from_angle(theta_deg: float) -> float:
    """
    Calculate displacement power factor from the V–I phase angle.

    Formula:  PF = cos(θ)

    Args:
        theta_deg: Phase angle between voltage and current in degrees.
                   Must be in [−90, 90].

    Returns:
        Power factor PF, dimensionless in [0, 1].

    Raises:
        ValueError: If theta_deg is outside [−90, 90].

    Interview Note:
        A lagging power factor (θ > 0) indicates an inductive load (motor,
        transformer magnetising current).  A leading power factor (θ < 0)
        indicates a capacitive load.  Unity power factor (θ = 0°) means
        current and voltage are perfectly in phase — maximum energy transfer.
        cos(−θ) = cos(θ) so both leading and lagging loads produce the same
        magnitude of PF, but the sign of Q differs.
    """
    if not (-90.0 <= theta_deg <= 90.0):
        raise ValueError(
            f"Phase angle must be in [−90, 90] degrees, got {theta_deg}"
        )
    return math.cos(math.radians(theta_deg))


# ---------------------------------------------------------------------------
# Energy (kWh)
# ---------------------------------------------------------------------------

def energy_kwh(power_w: float, delta_t_s: float) -> float:
    """
    Calculate energy consumed over a time interval.

    Formula:  E = P × Δt / 3,600,000

    Args:
        power_w:   Average real power over the interval, in watts (W).
                   Must be >= 0.
        delta_t_s: Duration of the interval in seconds (s).  Must be >= 0.

    Returns:
        Energy E in kilowatt-hours (kWh).

    Raises:
        ValueError: If power_w < 0 or delta_t_s < 0.

    Interview Note:
        Energy is the time integral of power.  The divisor 3,600,000 converts
        W·s (joules) to kWh: 1 kWh = 1000 W × 3600 s = 3,600,000 J.
        In a real metering system this integral is computed over each demand
        interval (typically 15 min) and accumulated by the revenue meter.
    """
    if power_w < 0:
        raise ValueError(f"Power must be >= 0 W, got {power_w}")
    if delta_t_s < 0:
        raise ValueError(f"Time interval must be >= 0 s, got {delta_t_s}")
    return power_w * delta_t_s / 3_600_000.0


# ---------------------------------------------------------------------------
# Load Percentage
# ---------------------------------------------------------------------------

def load_percentage(I_actual: float, I_rated: float) -> float:
    """
    Calculate a circuit's load as a percentage of its rated current.

    Formula:  Load% = (I_actual / I_rated) × 100

    Args:
        I_actual: Actual measured current in amps (A).  Must be >= 0.
        I_rated:  Rated (nameplate) current in amps (A).  Must be > 0.

    Returns:
        Load percentage (%).  Values > 100 % indicate an overloaded circuit.

    Raises:
        ValueError: If I_actual < 0 or I_rated <= 0.

    Interview Note:
        Load percentage tells you how close a circuit is to its thermal
        capacity.  NEC 310 requires continuous loads to be derated to 80 % of
        conductor ampacity, so a breaker rated 30 A should not carry more than
        24 A continuously.  Values > 110 % warrant a WARNING; > 125 % warrant
        a FAULT and may cause nuisance tripping or conductor overheating.
    """
    if I_actual < 0:
        raise ValueError(f"Actual current must be >= 0 A, got {I_actual}")
    if I_rated <= 0:
        raise ValueError(f"Rated current must be > 0 A, got {I_rated}")
    return (I_actual / I_rated) * 100.0


# ---------------------------------------------------------------------------
# Voltage Deviation (%)
# ---------------------------------------------------------------------------

def voltage_deviation_pct(V_actual: float, V_nominal: float) -> float:
    """
    Calculate the signed percentage deviation of voltage from nominal.

    Formula:  dev% = (V_actual − V_nominal) / V_nominal × 100

    Args:
        V_actual:  Measured RMS voltage in volts (V).
        V_nominal: Nominal (design) voltage in volts (V).  Must be > 0.

    Returns:
        Signed deviation in percent (%).
        Negative values indicate under-voltage; positive indicate over-voltage.

    Raises:
        ValueError: If V_nominal <= 0.

    Interview Note:
        ANSI C84.1 defines acceptable voltage tolerances for utilization
        equipment.  For 480 V systems, Range A (preferred) allows ±5 % at the
        point of utilization.  Range B (emergency) allows −8.3 % to +5.8 %.
        Under-voltage causes motors to draw higher current (to maintain
        torque), increasing heat and reducing motor life.
    """
    if V_nominal <= 0:
        raise ValueError(f"Nominal voltage must be > 0 V, got {V_nominal}")
    return (V_actual - V_nominal) / V_nominal * 100.0


# ---------------------------------------------------------------------------
# Three-Phase Real Power (balanced approximation)
# ---------------------------------------------------------------------------

def three_phase_power(V_line: float, I_line: float, pf: float) -> float:
    """
    Calculate total 3-phase real power assuming a balanced, symmetrical load.

    Formula:  P = √3 × V_L × I_L × PF

    Args:
        V_line: Line-to-line (phase-to-phase) RMS voltage in volts (V).
                For a 277/480 V system, V_line = 480 V.  Must be >= 0.
        I_line: Line (phase) RMS current in amps (A).  Must be >= 0.
        pf:     Displacement power factor, dimensionless [0, 1].

    Returns:
        Total 3-phase real power P in watts (W).

    Raises:
        ValueError: If V_line or I_line is negative, or pf is outside [0, 1].

    Interview Note:
        The √3 (≈ 1.732) factor arises from the 120° phase displacement between
        the three phases in a balanced system.  When you sum the instantaneous
        power contributions of all three phases the phasor geometry yields a
        constant total power with a √3 multiplier on the line voltage and
        current product.  At 480 V, 200 A, PF = 0.90:
            P = 1.732 × 480 × 200 × 0.90 ≈ 149,731 W ≈ 149.7 kW.

        This formula is an approximation valid only for balanced loads.  For
        unbalanced systems use sum_phase_power() instead.
    """
    if V_line < 0:
        raise ValueError(f"Line voltage must be >= 0 V, got {V_line}")
    if I_line < 0:
        raise ValueError(f"Line current must be >= 0 A, got {I_line}")
    if not (0.0 <= pf <= 1.0):
        raise ValueError(f"Power factor must be in [0, 1], got {pf}")
    return math.sqrt(3.0) * V_line * I_line * pf


# ---------------------------------------------------------------------------
# Per-Phase Summation (unbalanced / exact)
# ---------------------------------------------------------------------------

def sum_phase_power(
    phases: list[tuple[float, float, float]],
) -> dict[str, float]:
    """
    Calculate aggregate 3-phase power by summing individual phase contributions.

    This is the accurate method for unbalanced loads.  The simulator introduces
    small per-phase variations via Gaussian noise, so this function is preferred
    over the balanced approximation (three_phase_power) for dashboard totals.

    Formula (per phase k):
        S_k = V_k × I_k                (apparent power, VA)
        P_k = V_k × I_k × PF_k        (real power, W)
        Q_k = sqrt(S_k² − P_k²)       (reactive power, VAR — nonnegative convention)

    Aggregates:
        P_total = P_A + P_B + P_C      (W)
        S_total = S_A + S_B + S_C      (VA)
        Q_total = Q_A + Q_B + Q_C      (VAR)
        PF_agg  = P_total / S_total    (dimensionless; 0.0 when S_total == 0)

    Args:
        phases: List of exactly three (V, I, PF) tuples, one per phase
                (order: A, B, C).
                    V   — RMS line-to-neutral voltage in volts (V), >= 0
                    I   — RMS line current in amps (A), >= 0
                    PF  — displacement power factor, dimensionless [0, 1]

    Returns:
        dict with keys:
            "P_total"  — total real power (W)
            "S_total"  — total apparent power (VA)
            "Q_total"  — total reactive power (VAR, nonnegative)
            "PF_agg"   — aggregate power factor = P_total / S_total

    Raises:
        ValueError: If phases does not contain exactly 3 tuples, or if any
                    individual value fails the validation of the underlying
                    real_power / apparent_power / reactive_power functions.

    Assumptions:
        • Sinusoidal steady-state — no harmonic distortion modeled.
        • Reactive power is nonnegative (magnitude only).  The sign of Q
          (lagging vs. leading) is not tracked because individual phase PF
          angles are not available from the simulator.
        • The aggregate PF is an equivalent single-number representation of
          the combined load; it equals the true balanced-system PF only when
          all three phases are identical.

    Interview Note:
        In a real unbalanced system (e.g. single-phase loads distributed across
        phases, or a faulted phase), each phase may carry a different current
        and present a different power factor.  Summing per-phase contributions
        directly is more accurate than using average I and average PF in the
        balanced formula, because the balanced formula implicitly assumes
        V_A = V_B = V_C and I_A = I_B = I_C.  The error is small for slightly
        unbalanced systems (< 1 %) but grows with imbalance.
    """
    if len(phases) != 3:
        raise ValueError(f"Expected exactly 3 phase tuples, got {len(phases)}")

    P_total = 0.0
    S_total = 0.0
    Q_total = 0.0

    for V, I, pf in phases:
        S_k = apparent_power(V, I)
        P_k = real_power(V, I, pf)
        Q_k = reactive_power(P_k, S_k)
        P_total += P_k
        S_total += S_k
        Q_total += Q_k

    PF_agg = P_total / S_total if S_total > 0.0 else 0.0

    return {
        "P_total": P_total,
        "S_total": S_total,
        "Q_total": Q_total,
        "PF_agg":  PF_agg,
    }
