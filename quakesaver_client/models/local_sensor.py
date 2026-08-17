"""Sensor on the local network."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from uuid import uuid4

import requests
from obspy import Stream, read
from pydantic import Extra

from quakesaver_client.client_websocket import WebsocketHandler
from quakesaver_client.fdsnws import FDSNWSDataselectQuery
from quakesaver_client.fdsnws import dataselect as fdsnws_dataselect
from quakesaver_client.models.data_product_query import (
    DataProductQuery,
    EventRecordQueryResult,
    HVSpectraQueryResult,
    NoiseAutocorrelationQueryResult,
)
from quakesaver_client.models.measurement import (
    MeasurementQuery,
    MeasurementQueryFull,
    MeasurementResult,
)
from quakesaver_client.models.sensor_state import SensorState
from quakesaver_client.types import StationDetailLevel

# A sensor on the local network only serves its own state and raw waveforms.
# Everything derived from them is computed by the backend.
_NO_MEASUREMENTS = (
    "Local sensors do not serve measurements. "
    "Use QSCloudClient to query them from the QuakeSaver backend."
)
_NO_DATA_PRODUCTS = (
    "Local sensors do not serve data products. "
    "Use QSCloudClient to query them from the QuakeSaver backend."
)
_NO_STATIONXML = (
    "Local sensors do not serve StationXML metadata. "
    "Use QSCloudClient to download it from the QuakeSaver backend."
)


class LocalSensor(SensorState):
    """A base schema for other schemas to derive from."""

    def __init__(self, **data: dict) -> None:
        """Create an instance of the class."""
        super().__init__(**data)
        self._url = None

    @classmethod
    def connect(cls, sensor_url: str) -> LocalSensor:
        """Get a sensor which is available at `sensor_url`."""
        url = f"http://{sensor_url}/state"
        response = requests.get(url)
        sensor = LocalSensor.parse_raw(response.text)
        sensor._url = sensor_url
        return sensor

    def _get_data_product(
        self,
        data_product_name: str,
        query: DataProductQuery,
    ) -> dict:
        """Request data products of the sensor.

        Raises:
            NotImplementedError: Local sensors do not serve data products.
        """
        raise NotImplementedError(_NO_DATA_PRODUCTS)

    def get_event_records(self, query: DataProductQuery) -> EventRecordQueryResult:
        """Get Event Records of the sensor.

        Args:
            query: The query parameters like time limit and time frame.

        Raises:
            NotImplementedError: Local sensors do not serve data products.
        """
        raise NotImplementedError(_NO_DATA_PRODUCTS)

    def get_hv_spectra(self, query: DataProductQuery) -> HVSpectraQueryResult:
        """Get HV Spectres of the sensor.

        Args:
            query: The query parameters like time limit and time frame.

        Raises:
            NotImplementedError: Local sensors do not serve data products.
        """
        raise NotImplementedError(_NO_DATA_PRODUCTS)

    def get_noise_autocorrelations(
        self, query: DataProductQuery
    ) -> NoiseAutocorrelationQueryResult:
        """Get the Event Records of the sensor.

        Args:
            query: The query parameters like time limit and time frame.

        Raises:
            NotImplementedError: Local sensors do not serve data products.
        """
        raise NotImplementedError(_NO_DATA_PRODUCTS)

    def _get_measurement(self, query: MeasurementQueryFull) -> MeasurementResult:
        """Request measurements of the sensor.

        Raises:
            NotImplementedError: Local sensors do not serve measurements.
        """
        raise NotImplementedError(_NO_MEASUREMENTS)

    def get_peak_horizontal_acceleration(
        self, query: MeasurementQuery
    ) -> MeasurementResult:
        """Get the PGA measurement of the sensor.

        Args:
            query: The query parameters like time frame and aggregator.

        Raises:
            NotImplementedError: Local sensors do not serve measurements.
        """
        raise NotImplementedError(_NO_MEASUREMENTS)

    def get_jma_intensity(self, query: MeasurementQuery) -> MeasurementResult:
        """Get the JMA Intensity measurement of the sensor.

        Args:
            query: The query parameters like time frame and aggregator.

        Raises:
            NotImplementedError: Local sensors do not serve measurements.
        """
        raise NotImplementedError(_NO_MEASUREMENTS)

    def get_rms_amplitude(self, query: MeasurementQuery) -> MeasurementResult:
        """Get the RMS Amplitude measurement of the sensor.

        Args:
            query: The query parameters like time frame and aggregator.

        Raises:
            NotImplementedError: Local sensors do not serve measurements.
        """
        raise NotImplementedError(_NO_MEASUREMENTS)

    def get_spectral_intensity(self, query: MeasurementQuery) -> MeasurementResult:
        """Get the Spectral Intensity measurement of the sensor.

        Args:
            query: The query parameters like time frame and aggregator.

        Raises:
            NotImplementedError: Local sensors do not serve measurements.
        """
        raise NotImplementedError(_NO_MEASUREMENTS)

    def get_rms_offset(self, query: MeasurementQuery) -> MeasurementResult:
        """Get the RMS Offset measurement of the sensor.

        Args:
            query: The query parameters like time frame and aggregator.

        Raises:
            NotImplementedError: Local sensors do not serve measurements.
        """
        raise NotImplementedError(_NO_MEASUREMENTS)

    def get_waveform_stream(self) -> WebsocketHandler:
        """Get a `WebsocketHandler` to serve waveform data."""
        return WebsocketHandler(self._url)

    def get_waveform_data(
        self,
        file: Path,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> Path:
        """Request FDSN data from sensors and save to buffer.

        Args:
            file (Path): Outfile to write MiniSEED to, if file can be a directory.
            start_time (datetime | None, optional): Start time, if `None` all
                available data is returned. Defaults to None.
            end_time (datetime | None, optional):  if `None` it defaults
                to the current time. Defaults to None. Defaults to None.

        Returns:
            Path: Written MiniSEED file.
        """
        logging.debug("requesting waveform data for sensor %s.", self.uid)

        if start_time and end_time and start_time > end_time:
            raise ValueError("start_time is before end_time")

        end_time = end_time or datetime.now(tz=timezone.utc)
        params = FDSNWSDataselectQuery(starttime=start_time, endtime=end_time)

        if file.is_dir():
            filename = file / f"mseed-tmp-{uuid4()}"
        else:
            filename = file

        with filename.open("wb") as buffer:
            out_name = fdsnws_dataselect(
                uri=f"http://{self._url}",
                params=params,
                buffer=buffer,
            )

        if file.is_dir():
            return filename.rename(file / out_name.replace(":", ""))
        return file

    def get_waveforms_obspy(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> Stream:
        """Request FDSN data from sensors and return as an ObsPy stream.

        Args:
            start_time (datetime | None, optional): Start time, if `None` all
                available data is returned. Defaults to None.
            end_time (datetime | None, optional):  if `None` it defaults
                to the current time. Defaults to None. Defaults to None.

        Returns:
            Stream: The retrieved waveform data as obspy.stream.
        """
        logging.debug("requesting waveform data for sensor %s.", self.uid)
        if start_time and end_time and start_time > end_time:
            raise ValueError("start_time is before end_time")

        end_time = end_time or datetime.now(tz=timezone.utc)
        params = FDSNWSDataselectQuery(starttime=start_time, endtime=end_time)

        buffer = BytesIO()
        fdsnws_dataselect(
            uri=f"http://{self._url}",
            params=params,
            buffer=buffer,
        )
        buffer.flush()
        buffer.seek(0)

        return read(buffer)

    def get_stationxml(
        self,
        start_time: datetime,
        end_time: datetime,
        minlatitude: float = -90,
        maxlatitude: float = 90,
        minlongitude: float = -180,
        maxlongitude: float = 180,
        level: StationDetailLevel = "station",
        location_to_store: Path | str = None,
    ) -> Path:
        """Request FDSN StationXML metadata of the sensor.

        Raises:
            NotImplementedError: Local sensors do not serve StationXML.
        """
        raise NotImplementedError(_NO_STATIONXML)

    class Config:  # noqa
        """Configuration subclass for pydantics BaseModel."""

        extra = Extra.allow
        underscore_attrs_are_private = True
