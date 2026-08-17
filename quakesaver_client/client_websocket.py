"""Manage sensor websocket connections."""

from __future__ import annotations

import asyncio
import base64
import gzip
import logging
import random
from datetime import timedelta
from typing import Any, AsyncIterator

import aiohttp
import numpy as np
from obspy import Stream, Trace, UTCDateTime
from obspy.core import Stats

from quakesaver_client.models.data_products import DataUnit

from .models.data_products import TraceModel as TraceModelBase
from .models.websocket import WebSocketPayload, WebSocketRequest

logger = logging.getLogger(__name__)


DTYPE_MAP: dict[DataUnit, Any] = {
    DataUnit.counts: np.int32,
    DataUnit.m_s: float,
    DataUnit.m_s2: float,
}


START_ACTION = WebSocketRequest(action="startWaveformStream")
STOP_ACTION = WebSocketRequest(action="stopWaveformStream")

# A sensor can be rebooting or off the network for a while, so reconnect
# attempts are spaced out exponentially instead of retried in a tight loop.
RECONNECT_INITIAL_DELAY = 1.0  # seconds
RECONNECT_MAX_DELAY = 60.0  # seconds
RECONNECT_BACKOFF_FACTOR = 2.0


class TraceModel(TraceModelBase):
    """Trace model."""

    def _convert_waveform_data(self) -> None:
        """Convert received binary channel data to np.ndarrays."""
        for channel, data in self.data.items():
            if not isinstance(data, bytes):
                continue
            data = base64.b64decode(data)
            if self.compressed:
                data = gzip.decompress(data)
            self.data[channel] = np.frombuffer(data, dtype=DTYPE_MAP[self.data_unit])

        if self.compressed:
            self.compressed = False

    def as_stream(self) -> Stream:
        """Convert model to an obspy.Stream."""
        traces = []
        for channel, data in self.data.items():
            if not isinstance(data, np.ndarray):
                continue
            stats = Stats()
            stats.network = "QS"
            stats.station = self.uid
            stats.location = ""
            stats.channel = channel
            stats.npts = data.size
            stats.sampling_rate = 1.0 / self.delta_t
            stats.starttime = UTCDateTime(
                self.endtime - timedelta(seconds=self.delta_t * data.size)
            )
            traces.append(Trace(data, header=stats))
        return Stream(traces=traces)


class WebsocketHandler:
    """Manage a sensor websocket connection."""

    def __init__(self, url: str = "qssensor.local") -> None:
        """Initialize `WebsocketHandler`.

        Args:
            url: hostname (without protocol and route).
        """
        self._session = None
        self.url = url

    async def create_websocket(
        self, session: aiohttp.ClientSession
    ) -> AsyncIterator[TraceModel]:
        """Create a websocket the yields data chunks as `TraceModel` instances."""
        async with session.ws_connect(f"ws://{self.url}/ws") as ws:
            await ws.send_str(START_ACTION.json())

            async for msg in ws:
                data = WebSocketPayload.parse_raw(msg.data)

                if "data" not in data.payload:
                    continue

                trace = TraceModel(**data.payload)
                trace._convert_waveform_data()
                logger.debug(f"received data from uid: {trace.uid}")
                yield trace

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    async def start(self) -> AsyncIterator[TraceModel]:
        """Start the websocket connection.

        Reconnects indefinitely when the sensor drops the connection, waiting
        longer after each failed attempt up to `RECONNECT_MAX_DELAY`. The delay
        is reset as soon as the sensor delivers data again.
        """
        session = self._get_session()
        delay = RECONNECT_INITIAL_DELAY
        async with session:
            while True:
                try:
                    async for trace in self.create_websocket(session):
                        delay = RECONNECT_INITIAL_DELAY
                        yield trace
                except aiohttp.ClientError as e:
                    logger.warning("Websocket connection to %s failed: %s", self.url, e)
                except Exception as e:
                    logger.exception("Unexpected websocket error: %s", e)
                else:
                    logger.info("Sensor %s closed the websocket.", self.url)

                # Spread reconnects out a little so that many clients losing the
                # same sensor do not retry in lockstep.
                wait = delay * (0.5 + random.random() / 2)
                logger.debug("Reconnecting to %s in %.1f s.", self.url, wait)
                await asyncio.sleep(wait)
                delay = min(delay * RECONNECT_BACKOFF_FACTOR, RECONNECT_MAX_DELAY)

    async def stop(self) -> None:
        """Stop the websocket connection."""
        session = self._get_session()
        async with session:
            async with session.ws_connect(f"ws://{self.url}/ws") as ws:
                await ws.send_str(STOP_ACTION.json())
