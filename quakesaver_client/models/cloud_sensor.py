"""Module containing the sensor model."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import requests
from pydantic import Extra, ValidationError

from quakesaver_client.errors import CorruptedDataError
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
from quakesaver_client.models.permission import Permission
from quakesaver_client.models.sensor_state import SensorState
from quakesaver_client.models.warnings import SensorWarnings
from quakesaver_client.types import StationDetailLevel
from quakesaver_client.util import assure_output_path, handle_response

if TYPE_CHECKING:
    from quakesaver_client import QSCloudClient


class CloudSensor(SensorState):
    """A base schema for other schemas to derive from."""

    _client: QSCloudClient
    _api_base_url: str
    _fdsn_base_url: str

    first_seen: datetime
    last_updated: datetime
    permission: Permission
    warnings: SensorWarnings
    max_data_product_count: int

    def __init__(
        self: CloudSensor,
        api_base_url: str,
        fdsn_base_url: str,
        client: QSCloudClient,
        **data: dict,
    ) -> None:
        """Create an instance of the class."""
        super().__init__(**data)
        self._client = client
        self._api_base_url = api_base_url
        self._fdsn_base_url = fdsn_base_url

    @property
    def _headers(self: CloudSensor) -> dict:
        """The authorization headers, renewing the session token if needed."""
        return self._client._get_authorization_headers()

    def _get_data_product(
        self: CloudSensor,
        data_product_name: str,
        query: DataProductQuery,
    ) -> dict:
        """Request data products of the sensor."""
        logging.debug(
            "QSCloudClient requesting data product %s for sensor %s.",
            data_product_name,
            self.uid,
        )
        response = requests.post(
            url=f"{self._api_base_url}/sensors/{self.uid}/data_products/{data_product_name}",
            headers=self._headers,
            params=query.dict(),
            data=[],
        )
        response_data = handle_response(response)
        return response_data

    def get_event_records(
        self: CloudSensor, query: DataProductQuery
    ) -> EventRecordQueryResult:
        """Get Event Records of the sensor.

        Args:
            query: The query parameters like time limit and time frame.

        Returns:
            EventRecordQueryResult: The queried data products.
        """
        result = self._get_data_product("EventRecord", query)

        try:
            result = EventRecordQueryResult.parse_obj(result)
        except ValidationError as e:
            raise CorruptedDataError() from e
        return result

    def get_hv_spectra(
        self: CloudSensor, query: DataProductQuery
    ) -> HVSpectraQueryResult:
        """Get HV Spectres of the sensor.

        Args:
            query: The query parameters like time limit and time frame.

        Returns:
            HVSpectraQueryResult: The queried data products.
        """
        result = self._get_data_product("HVSpectra", query)

        try:
            result = HVSpectraQueryResult.parse_obj(result)
        except ValidationError as e:
            raise CorruptedDataError() from e
        return result

    def get_noise_autocorrelations(
        self: CloudSensor, query: DataProductQuery
    ) -> NoiseAutocorrelationQueryResult:
        """Get the Event Records of the sensor.

        Args:
            query: The query parameters like time limit and time frame.

        Returns:
            NoiseAutocorrelationQueryResult: The queried data products.
        """
        result = self._get_data_product("NoiseAutocorrelation", query)

        try:
            result = NoiseAutocorrelationQueryResult.parse_obj(result)
        except ValidationError as e:
            raise CorruptedDataError() from e
        return result

    def _get_measurement(
        self: CloudSensor, query: MeasurementQueryFull
    ) -> MeasurementResult:
        """Request measurements of the sensor."""
        logging.debug("QSCloudClient requesting measurement for sensor %s.", self.uid)
        response = requests.post(
            url=f"{self._api_base_url}/sensors/{self.uid}/measurements",
            headers=self._headers,
            data=query.json(),
        )
        response_data = handle_response(response)
        try:
            result = MeasurementResult(**response_data)
        except ValidationError as e:
            raise CorruptedDataError() from e
        return result

    def get_peak_horizontal_acceleration(
        self: CloudSensor, query: MeasurementQuery
    ) -> MeasurementResult:
        """Get the PGA measurement of the sensor.

        Args:
            query: The query parameters like time frame and aggregator.

        Returns:
            MeasurementQuery: The queried data (if exists) as time series.
        """
        full_query = MeasurementQueryFull(
            **query.dict(), field="pga", measurement="rt_peak_ground_motion"
        )
        return self._get_measurement(query=full_query)

    def get_jma_intensity(
        self: CloudSensor, query: MeasurementQuery
    ) -> MeasurementResult:
        """Get the JMA Intensity measurement of the sensor.

        Args:
            query: The query parameters like time frame and aggregator.

        Returns:
            MeasurementQuery: The queried data (if exists) as time series.
        """
        full_query = MeasurementQueryFull(
            **query.dict(), field="intensity", measurement="rt_jma_intensity"
        )
        return self._get_measurement(query=full_query)

    def get_rms_amplitude(
        self: CloudSensor, query: MeasurementQuery
    ) -> MeasurementResult:
        """Get the RMS Amplitude measurement of the sensor.

        Args:
            query: The query parameters like time frame and aggregator.

        Returns:
            MeasurementQuery: The queried data (if exists) as time series.
        """
        full_query = MeasurementQueryFull(
            **query.dict(), field="rms_amplitude", measurement="rms_amplitude"
        )
        return self._get_measurement(query=full_query)

    def get_spectral_intensity(
        self: CloudSensor, query: MeasurementQuery
    ) -> MeasurementResult:
        """Get the Spectral Intensity measurement of the sensor.

        Args:
            query: The query parameters like time frame and aggregator.

        Returns:
            MeasurementQuery: The queried data (if exists) as time series.
        """
        full_query = MeasurementQueryFull(
            **query.dict(),
            field="spectral_intensity",
            measurement="rt_spectral_intensity",
        )
        return self._get_measurement(query=full_query)

    def get_rms_offset(self: CloudSensor, query: MeasurementQuery) -> MeasurementResult:
        """Get the RMS Offset measurement of the sensor.

        Args:
            query: The query parameters like time frame and aggregator.

        Returns:
            MeasurementQuery: The queried data (if exists) as time series.
        """
        full_query = MeasurementQueryFull(
            **query.dict(), field="rms_offset", measurement="chrony"
        )
        return self._get_measurement(query=full_query)

    def get_waveform_data(
        self: CloudSensor,
        start_time: datetime,
        end_time: datetime,
        location_to_store: Path | str = None,
    ) -> Path | None:
        """Request FDSN waveform dat of the sensor."""
        logging.debug("QSCloudClient requesting waveform data for sensor %s.", self.uid)

        location_to_store = assure_output_path(location_to_store)

        params = {"starttime": start_time, "endtime": end_time, "sensor_uids": self.uid}
        response = requests.get(
            url=f"{self._fdsn_base_url}/dataselect/1/queryauth_jwt_by_id",
            headers=self._headers,
            params=params,
        )

        if response.status_code != 200:
            raise CorruptedDataError(response.text)

        filename = response.headers.get(
            "Content-Disposition", "filename=qsdata.mseed"
        ).split("=")[1]
        storage_path = location_to_store / filename
        with open(storage_path, "wb") as file:
            file.write(response.content)
        return storage_path

    def get_stationxml(
        self: CloudSensor,
        start_time: datetime,
        end_time: datetime,
        minlatitude: float = -90,
        maxlatitude: float = 90,
        minlongitude: float = -180,
        maxlongitude: float = 180,
        level: StationDetailLevel = "station",
        location_to_store: Path | str = None,
    ) -> Path:
        """Request FDSN StationXML metadata of the sensor."""
        logging.debug("QSCloudClient requesting stationxml for sensor %s.", self.uid)

        location_to_store = assure_output_path(location_to_store)

        params = {
            "starttime": start_time,
            "endtime": end_time,
            "sensor_uids": self.uid,
            "minlatitude": minlatitude,
            "maxlatitude": maxlatitude,
            "minlongitude": minlongitude,
            "maxlongitude": maxlongitude,
            "level": level,
        }
        response = requests.get(
            url=f"{self._fdsn_base_url}/station/1/queryauth_jwt_by_id",
            headers=self._headers,
            params=params,
        )

        if response.status_code != 200:
            raise CorruptedDataError(response.text)

        filename = response.headers["Content-Disposition"].split("=")[1]
        storage_path = location_to_store / filename
        with open(storage_path, "wb") as file:
            file.write(response.content)
        return storage_path

    class Config:  # noqa
        """Configuration subclass for pydantics BaseModel."""

        extra = Extra.allow
        underscore_attrs_are_private = True
