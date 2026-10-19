"""
tests/test_calculations.py

Unit tests for calculations.py.
All floating-point comparisons use pytest.approx().
Parametrize is used for boundary and multi-case coverage.
"""

import math

import pytest

from calculations import (
    apparent_power,
    energy_kwh,
    load_percentage,
    power_factor_from_angle,
    reactive_power,
    real_power,
    sum_phase_power,
    three_phase_power,
    voltage_deviation_pct,
)

# ---------------------------------------------------------------------------
# apparent_power
# ---------------------------------------------------------------------------

class TestApparentPower:
    def test_nominal(self):
        assert apparent_power(277, 160) == pytest.approx(44320.0)

    def test_zero_current(self):
        assert apparent_power(277, 0) == pytest.approx(0.0)

    def test_zero_voltage(self):
        assert apparent_power(0, 160) == pytest.approx(0.0)

    def test_negative_voltage_raises(self):
        with pytest.raises(ValueError):
            apparent_power(-1, 160)

    def test_negative_current_raises(self):
        with pytest.raises(ValueError):
            apparent_power(277, -1)


# ---------------------------------------------------------------------------
# real_power
# ---------------------------------------------------------------------------

class TestRealPower:
    def test_nominal(self):
        assert real_power(277, 160, 0.88) == pytest.approx(39001.6)

    def test_unity_pf(self):
        assert real_power(277, 160, 1.0) == pytest.approx(44320.0)

    def test_zero_pf(self):
        assert real_power(277, 160, 0.0) == pytest.approx(0.0)

    def test_pf_above_one_raises(self):
        with pytest.raises(ValueError):
            real_power(277, 160, 1.01)

    def test_negative_pf_raises(self):
        with pytest.raises(ValueError):
            real_power(277, 160, -0.1)

    @pytest.mark.parametrize("V, I, pf, expected", [
        (480, 200, 0.90, 86400.0),
        (277,   0, 0.85,     0.0),
    ])
    def test_parametrize(self, V, I, pf, expected):
        assert real_power(V, I, pf) == pytest.approx(expected)


# ---------------------------------------------------------------------------
# reactive_power
# ---------------------------------------------------------------------------

class TestReactivePower:
    def test_nominal(self):
        P = 39001.6
        S = 44320.0
        expected = math.sqrt(S ** 2 - P ** 2)
        assert reactive_power(P, S) == pytest.approx(expected, rel=1e-6)

    def test_unity_pf(self):
        # When S == P (PF = 1), Q must be exactly 0
        assert reactive_power(44320.0, 44320.0) == pytest.approx(0.0, abs=1e-9)

    def test_zero(self):
        assert reactive_power(0.0, 0.0) == pytest.approx(0.0)

    def test_s_less_than_p_raises(self):
        with pytest.raises(ValueError):
            reactive_power(100.0, 90.0)

    def test_power_triangle_identity(self):
        P = 30_000.0
        S = 35_000.0
        Q = reactive_power(P, S)
        assert P ** 2 + Q ** 2 == pytest.approx(S ** 2, rel=1e-6)


# ---------------------------------------------------------------------------
# power_factor_from_angle
# ---------------------------------------------------------------------------

class TestPowerFactorFromAngle:
    @pytest.mark.parametrize("theta, expected", [
        (0,  1.0),
        (30, pytest.approx(math.cos(math.radians(30)), rel=1e-6)),
        (60, pytest.approx(math.cos(math.radians(60)), rel=1e-6)),
        (90, pytest.approx(0.0, abs=1e-9)),
    ])
    def test_standard_angles(self, theta, expected):
        assert power_factor_from_angle(theta) == expected

    def test_negative_angle(self):
        # cos(-30) == cos(30)
        assert power_factor_from_angle(-30) == pytest.approx(
            math.cos(math.radians(30)), rel=1e-6
        )

    @pytest.mark.parametrize("theta", [91, -91])
    def test_angle_too_large_raises(self, theta):
        with pytest.raises(ValueError):
            power_factor_from_angle(theta)


# ---------------------------------------------------------------------------
# energy_kwh
# ---------------------------------------------------------------------------

class TestEnergyKwh:
    def test_nominal(self):
        # 1 000 W for 3 600 s (1 hour) = 1.0 kWh
        assert energy_kwh(1_000.0, 3_600.0) == pytest.approx(1.0)

    def test_zero_time(self):
        assert energy_kwh(5_000.0, 0.0) == pytest.approx(0.0)

    def test_three_second_tick(self):
        expected = 50_000.0 * 3.0 / 3_600_000.0
        assert energy_kwh(50_000.0, 3.0) == pytest.approx(expected, rel=1e-9)

    def test_negative_power_raises(self):
        with pytest.raises(ValueError):
            energy_kwh(-1.0, 3.0)

    def test_negative_time_raises(self):
        with pytest.raises(ValueError):
            energy_kwh(1_000.0, -1.0)


# ---------------------------------------------------------------------------
# load_percentage
# ---------------------------------------------------------------------------

class TestLoadPercentage:
    def test_nominal(self):
        assert load_percentage(160, 200) == pytest.approx(80.0)

    def test_at_rated(self):
        assert load_percentage(200, 200) == pytest.approx(100.0)

    def test_overcurrent(self):
        assert load_percentage(250, 200) == pytest.approx(125.0)

    def test_zero_actual(self):
        assert load_percentage(0, 200) == pytest.approx(0.0)

    def test_zero_rated_raises(self):
        with pytest.raises(ValueError):
            load_percentage(100, 0)


# ---------------------------------------------------------------------------
# voltage_deviation_pct
# ---------------------------------------------------------------------------

class TestVoltageDeviationPct:
    def test_nominal(self):
        assert voltage_deviation_pct(277, 277) == pytest.approx(0.0)

    def test_undervoltage(self):
        # 277 * 0.90 = 249.3 → deviation = -10 %
        assert voltage_deviation_pct(277 * 0.90, 277) == pytest.approx(-10.0, rel=1e-3)

    def test_overvoltage(self):
        result = voltage_deviation_pct(290, 277)
        assert result > 0

    def test_zero_nominal_raises(self):
        with pytest.raises(ValueError):
            voltage_deviation_pct(277, 0)

    def test_sign_convention(self):
        # Under-voltage must be negative
        assert voltage_deviation_pct(250, 277) < 0


# ---------------------------------------------------------------------------
# three_phase_power
# ---------------------------------------------------------------------------

class TestThreePhasePower:
    def test_nominal(self):
        expected = math.sqrt(3) * 480 * 200 * 0.90
        assert three_phase_power(480, 200, 0.90) == pytest.approx(expected, rel=1e-6)

    def test_unity_pf(self):
        expected = math.sqrt(3) * 480 * 200
        assert three_phase_power(480, 200, 1.0) == pytest.approx(expected, rel=1e-6)

    def test_zero_current(self):
        assert three_phase_power(480, 0, 0.85) == pytest.approx(0.0)

    def test_negative_voltage_raises(self):
        with pytest.raises(ValueError):
            three_phase_power(-480, 200, 0.9)

    def test_pf_out_of_range_raises(self):
        with pytest.raises(ValueError):
            three_phase_power(480, 200, 1.1)


# ---------------------------------------------------------------------------
# sum_phase_power
# ---------------------------------------------------------------------------

class TestSumPhasePower:
    """Tests for per-phase summation (sum_phase_power)."""

    # --- helpers ---
    BALANCED = [(277.0, 160.0, 0.88)] * 3   # identical phases

    def test_balanced_p_total(self):
        # P_total should equal 3 × (V × I × PF)
        result = sum_phase_power(self.BALANCED)
        expected_P = 3 * 277.0 * 160.0 * 0.88
        assert result["P_total"] == pytest.approx(expected_P, rel=1e-6)

    def test_balanced_s_total(self):
        result = sum_phase_power(self.BALANCED)
        expected_S = 3 * 277.0 * 160.0
        assert result["S_total"] == pytest.approx(expected_S, rel=1e-6)

    def test_balanced_pf_agg_equals_phase_pf(self):
        # For identical phases PF_agg must equal the per-phase PF
        result = sum_phase_power(self.BALANCED)
        assert result["PF_agg"] == pytest.approx(0.88, rel=1e-6)

    def test_power_triangle_identity_aggregate(self):
        # P_total^2 + Q_total^2 is NOT necessarily equal to S_total^2 for
        # summed phases (Q_total is sum of per-phase magnitudes, not vector sum),
        # but each individual phase satisfies P_k^2 + Q_k^2 = S_k^2.
        result = sum_phase_power(self.BALANCED)
        P = result["P_total"] / 3
        S = result["S_total"] / 3
        Q = result["Q_total"] / 3
        assert P**2 + Q**2 == pytest.approx(S**2, rel=1e-6)

    def test_unbalanced_p_total(self):
        # Phase A: heavy load; Phase B: light load; Phase C: nominal
        phases = [
            (277.0, 200.0, 0.90),   # Phase A — overcurrent
            (277.0,  80.0, 0.95),   # Phase B — lightly loaded
            (277.0, 160.0, 0.88),   # Phase C — nominal
        ]
        result = sum_phase_power(phases)
        expected_P = (277*200*0.90) + (277*80*0.95) + (277*160*0.88)
        assert result["P_total"] == pytest.approx(expected_P, rel=1e-6)

    def test_unbalanced_pf_agg(self):
        phases = [
            (277.0, 200.0, 0.90),
            (277.0,  80.0, 0.95),
            (277.0, 160.0, 0.88),
        ]
        result = sum_phase_power(phases)
        expected_P = (277*200*0.90) + (277*80*0.95) + (277*160*0.88)
        expected_S = (277*200)      + (277*80)       + (277*160)
        assert result["PF_agg"] == pytest.approx(expected_P / expected_S, rel=1e-6)

    def test_zero_current_all_phases(self):
        phases = [(277.0, 0.0, 0.88)] * 3
        result = sum_phase_power(phases)
        assert result["P_total"] == pytest.approx(0.0)
        assert result["S_total"] == pytest.approx(0.0)
        assert result["Q_total"] == pytest.approx(0.0)
        assert result["PF_agg"]  == pytest.approx(0.0)   # S_total=0 → safe fallback

    def test_unity_pf_all_phases(self):
        phases = [(277.0, 160.0, 1.0)] * 3
        result = sum_phase_power(phases)
        assert result["Q_total"] == pytest.approx(0.0, abs=1e-6)
        assert result["PF_agg"]  == pytest.approx(1.0, rel=1e-6)

    def test_wrong_phase_count_raises(self):
        with pytest.raises(ValueError):
            sum_phase_power([(277.0, 160.0, 0.88)] * 2)

    def test_wrong_phase_count_4_raises(self):
        with pytest.raises(ValueError):
            sum_phase_power([(277.0, 160.0, 0.88)] * 4)

    def test_balanced_vs_three_phase_formula(self):
        """
        For a perfectly balanced load, sum_phase_power P_total should be close
        to the balanced formula P = sqrt(3) * V_LL * I_L * PF.

        V_LL = sqrt(3) * V_LN, so:
            three_phase_power(sqrt(3)*277, 160, 0.88)
            == sqrt(3) * sqrt(3)*277 * 160 * 0.88
            == 3 * 277 * 160 * 0.88
            == sum_phase_power([(277, 160, 0.88)] * 3)["P_total"]
        """
        V_LN = 277.0
        I    = 160.0
        PF   = 0.88
        V_LL = math.sqrt(3) * V_LN

        p_sum       = sum_phase_power([(V_LN, I, PF)] * 3)["P_total"]
        p_balanced  = three_phase_power(V_LL, I, PF)
        assert p_sum == pytest.approx(p_balanced, rel=1e-6)
