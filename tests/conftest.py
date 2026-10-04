"""Shared fixtures for the MyPV ELWA 2 Modbus tests."""

from collections.abc import Iterator
from unittest.mock import patch

import pytest

COORDINATOR_CLOCK = "custom_components.mypv_elwa2_modbus.coordinator._monotonic_clock"


class FakeClock:
    """A controllable replacement for the coordinator's poll-interval clock."""

    def __init__(self, start: float = 1000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def fake_clock() -> Iterator[FakeClock]:
    """Replace only the coordinator's poll clock; the event loop keeps real time."""
    clock = FakeClock()
    with patch(COORDINATOR_CLOCK, clock):
        yield clock
