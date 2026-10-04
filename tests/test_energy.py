"""Unit tests for the energy integration math (no Home Assistant needed)."""

import pytest

from custom_components.mypv_elwa2_modbus.util import integrate_energy_kwh


def test_power_is_integrated_over_one_hour():
    assert integrate_energy_kwh(0.0, 3600, 3600) == pytest.approx(3.6)


def test_small_interval_adds_proportional_energy():
    assert integrate_energy_kwh(1.0, 3000, 5) == pytest.approx(1.0 + 3000 * 5 / 3600 / 1000)


def test_zero_power_adds_nothing():
    assert integrate_energy_kwh(2.5, 0, 60) == 2.5
