"""local sensor tests."""

import datetime
from typing import Callable

import numpy as np
import pytest

from quakesaver_client import LocalSensor


@pytest.fixture()
def local_test_sensor() -> LocalSensor:
    """Get a local sensor for testing."""
    return LocalSensor.connect("localhost:5533")


SCALE_FACTOR: dict[int, float] = {2: 3.9e-6, 4: 7.8e-6, 8: 15.6e-6}


def convert_to_acceleration(data: np.ndarray[int]):
    return data * 3.9e-6  # Valid for range +- 2g


@pytest.mark.local
async def test_stream(local_test_sensor: Callable) -> None:
    """Connect to a sensor on the local network."""
    stream = local_test_sensor.get_waveform_stream()

    async for trace_segment in stream.start():
        assert not trace_segment.compressed
        # print(trace.data['EN1'])
        # if trace_segment:
        #     await stream.stop()
        #     break

        # according to casing labels
        # EN1 -> x
        # EN2 -> y
        # EN3 -> z


@pytest.mark.local
async def test_waveform_fetch(local_test_sensor: Callable) -> None:
    """Connect to a sensor on the local network."""
    tmax = datetime.datetime.utcnow()
    tmin = tmax - datetime.timedelta(minutes=1)
    data = local_test_sensor.get_waveform_data(tmin, tmax)
    assert data


@pytest.mark.local
async def test_waveform_obspy(local_test_sensor: Callable) -> None:
    """Connect to a sensor on the local network."""
    tmax = datetime.datetime.utcnow()
    tmin = tmax - datetime.timedelta(minutes=1)
    data = local_test_sensor.get_waveforms_obspy(tmin, tmax)
    assert data
