"""
tests/test_energy_accumulation.py

Unit tests for energy accumulation logic.

These tests verify:
  1. energy_kwh() correctness for known P and delta_t values.
  2. The pause/resume pattern used in app.py:
       - energy does not accumulate while paused (last_tick_time reset to None)
       - the first tick after startup / resume does not accumulate energy
       - resuming does not include paused duration
       - negative delta_t is clamped to zero
  3. Multiple tick accumulation.

The app's accumulation logic is extracted into a pure helper function
(_accumulate_energy) so it can be tested without Streamlit session state.
"""

import pytest

from calculations import energy_kwh


# ---------------------------------------------------------------------------
# Helper that mirrors the accumulation logic in app.py
# ---------------------------------------------------------------------------

def _accumulate_energy(
    energy_kwh_current: float,
    total_P_W: float,
    paused: bool,
    last_tick_time: float | None,
    current_tick_time: float,
) -> tuple[float, float | None]:
    """
    Pure reimplementation of app.py energy accumulation.

    Args:
        energy_kwh_current: Accumulated kWh before this tick.
        total_P_W:          Current total real power (W).
        paused:             Whether the simulation is paused.
        last_tick_time:     time.monotonic() value at previous tick, or None.
        current_tick_time:  time.monotonic() value at this tick.

    Returns:
        (new_energy_kwh, new_last_tick_time)
    """
    if not paused:
        if last_tick_time is not None:
            delta_t_s = current_tick_time - last_tick_time
            delta_t_s = max(0.0, delta_t_s)
            energy_kwh_current += energy_kwh(total_P_W, delta_t_s)
        new_last_tick_time = current_tick_time
    else:
        # Paused — reset clock so resumed tick does not include paused duration
        new_last_tick_time = None

    return energy_kwh_current, new_last_tick_time


# ---------------------------------------------------------------------------
# energy_kwh() correctness
# ---------------------------------------------------------------------------

class TestEnergyKwhAccumulation:
    def test_known_values(self):
        # 50 kW for 3 s → 50000 * 3 / 3_600_000
        result = energy_kwh(50_000.0, 3.0)
        assert result == pytest.approx(50_000.0 * 3.0 / 3_600_000.0, rel=1e-9)

    def test_one_hour_one_kw(self):
        assert energy_kwh(1_000.0, 3_600.0) == pytest.approx(1.0, rel=1e-9)

    def test_zero_power(self):
        assert energy_kwh(0.0, 10.0) == pytest.approx(0.0)

    def test_zero_time(self):
        assert energy_kwh(50_000.0, 0.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# First-tick guard (no unknown elapsed time on startup)
# ---------------------------------------------------------------------------

class TestFirstTickGuard:
    def test_no_accumulation_on_first_tick(self):
        """On the very first live tick last_tick_time is None → no energy added."""
        energy, new_ts = _accumulate_energy(
            energy_kwh_current=0.0,
            total_P_W=50_000.0,
            paused=False,
            last_tick_time=None,   # first run
            current_tick_time=1000.0,
        )
        assert energy == pytest.approx(0.0)
        assert new_ts == 1000.0

    def test_second_tick_accumulates(self):
        """Second tick has a known elapsed time and should accumulate energy."""
        energy, _ = _accumulate_energy(
            energy_kwh_current=0.0,
            total_P_W=50_000.0,
            paused=False,
            last_tick_time=1000.0,
            current_tick_time=1003.0,   # 3 s elapsed
        )
        expected = energy_kwh(50_000.0, 3.0)
        assert energy == pytest.approx(expected, rel=1e-9)


# ---------------------------------------------------------------------------
# Pause behaviour
# ---------------------------------------------------------------------------

class TestPauseBehaviour:
    def test_paused_energy_unchanged(self):
        """Energy must not increase while paused."""
        initial_energy = 0.005
        energy, new_ts = _accumulate_energy(
            energy_kwh_current=initial_energy,
            total_P_W=50_000.0,
            paused=True,
            last_tick_time=1000.0,
            current_tick_time=1003.0,
        )
        assert energy == pytest.approx(initial_energy)

    def test_paused_resets_clock(self):
        """Pausing must set last_tick_time to None."""
        _, new_ts = _accumulate_energy(
            energy_kwh_current=0.0,
            total_P_W=50_000.0,
            paused=True,
            last_tick_time=1000.0,
            current_tick_time=1003.0,
        )
        assert new_ts is None

    def test_resume_first_tick_no_accumulation(self):
        """
        The first tick after unpausing has last_tick_time=None (reset by pause).
        No energy should be accumulated for that tick.
        """
        # Simulate paused tick resetting clock
        _, ts_after_pause = _accumulate_energy(0.0, 50_000.0, True, 1000.0, 1003.0)
        assert ts_after_pause is None

        # First live tick after resume — should not accumulate
        energy_after_resume, ts_after_resume = _accumulate_energy(
            0.0, 50_000.0, False, ts_after_pause, 1060.0
        )
        assert energy_after_resume == pytest.approx(0.0)
        assert ts_after_resume == 1060.0

    def test_resume_second_tick_accumulates_only_live_time(self):
        """
        After pausing for 57 s and resuming, the second live tick should
        accumulate only the time between the two live ticks (3 s), not the
        paused time (57 s).
        """
        # Pause at t=1003
        _, ts_paused = _accumulate_energy(0.0, 50_000.0, True, 1000.0, 1003.0)

        # First live tick at t=1060 (57 s after pause — should NOT count)
        energy1, ts1 = _accumulate_energy(0.0, 50_000.0, False, ts_paused, 1060.0)
        assert energy1 == pytest.approx(0.0)

        # Second live tick at t=1063 (3 s after resume — SHOULD count)
        energy2, ts2 = _accumulate_energy(energy1, 50_000.0, False, ts1, 1063.0)
        expected = energy_kwh(50_000.0, 3.0)
        assert energy2 == pytest.approx(expected, rel=1e-9)


# ---------------------------------------------------------------------------
# Negative delta_t clamp
# ---------------------------------------------------------------------------

class TestNegativeDeltaTClamp:
    def test_negative_delta_t_clamped_to_zero(self):
        """
        If current_tick_time < last_tick_time (should never happen with
        monotonic clock but tested as a safety guard), energy must not decrease.
        """
        energy, _ = _accumulate_energy(
            energy_kwh_current=0.005,
            total_P_W=50_000.0,
            paused=False,
            last_tick_time=1005.0,
            current_tick_time=1003.0,   # earlier than last — delta_t = -2 s
        )
        assert energy == pytest.approx(0.005)   # unchanged


# ---------------------------------------------------------------------------
# Multi-tick accumulation
# ---------------------------------------------------------------------------

class TestMultiTickAccumulation:
    def test_three_ticks_total_energy(self):
        """Accumulate across three 3-second ticks at constant 50 kW."""
        P = 50_000.0
        energy = 0.0
        last_ts = None

        for tick_time in [1000.0, 1003.0, 1006.0, 1009.0]:
            energy, last_ts = _accumulate_energy(energy, P, False, last_ts, tick_time)

        # First tick: no accumulation; ticks 2, 3, 4: each 3 s at 50 kW
        expected = 3 * energy_kwh(P, 3.0)
        assert energy == pytest.approx(expected, rel=1e-9)

    def test_energy_does_not_accumulate_twice_per_tick(self):
        """
        Calling accumulate twice with the same current_tick_time (simulating
        an unexpected Streamlit double-run) accumulates only once because
        delta_t on the second call is 0.
        """
        P = 50_000.0
        energy, ts = _accumulate_energy(0.0, P, False, None, 1000.0)   # first tick
        energy, ts = _accumulate_energy(energy, P, False, ts, 1003.0)  # 3 s tick
        first_energy = energy
        energy, ts = _accumulate_energy(energy, P, False, ts, 1003.0)  # same time again
        assert energy == pytest.approx(first_energy)   # unchanged
