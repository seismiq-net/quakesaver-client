"""Package containing a client for the QuakeSaver application."""

from __future__ import annotations

import base64
import binascii
import json
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Callable, TypeVar

import requests
from pydantic import ValidationError

from quakesaver_client.errors import CorruptedDataError
from quakesaver_client.models.cloud_sensor import CloudSensor
from quakesaver_client.models.local_sensor import LocalSensor  # noqa
from quakesaver_client.models.token import Token
from quakesaver_client.util import handle_response

DecoratedFunction = TypeVar("DecoratedFunction", bound=Callable[..., Any])

# Renew shortly before the token actually expires, so that a request started
# just before the deadline is not rejected because of clock skew or latency.
TOKEN_REFRESH_MARGIN = timedelta(seconds=60)
# Assumed lifetime for tokens that carry no readable expiry claim.
DEFAULT_TOKEN_LIFETIME = timedelta(minutes=15)


def _read_token_expiry(token: Token) -> datetime | None:
    """Read the expiry claim of a JWT access token.

    Args:
        token: The token to inspect.

    Returns:
        datetime | None: The expiry time, or None if it cannot be determined.
    """
    try:
        payload = token.access_token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(payload))
        return datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
    except (
        IndexError,
        KeyError,
        TypeError,
        ValueError,
        OverflowError,
        OSError,
        binascii.Error,
    ):
        logging.debug("Could not read an expiry from the access token.")
        return None


def _needs_token(function: DecoratedFunction) -> DecoratedFunction:
    @wraps(function)
    def request_token_if_needed(
        self: QSCloudClient, *args: list, **kwargs: dict
    ) -> DecoratedFunction:
        if self._token_needs_renewal():
            logging.debug("QSCloudClient requesting user _token.")
            response = requests.post(
                url=f"{self._api_base_url}/user/get_token",
                data={"username": self._email, "password": self._password},
            )
            response_data = handle_response(response)
            try:
                token = Token(**response_data)
            except ValidationError as e:
                raise CorruptedDataError() from e
            self._token = token
            self._token_expires_at = _read_token_expiry(token) or (
                datetime.now(tz=timezone.utc) + DEFAULT_TOKEN_LIFETIME
            )

        return function(self, *args, **kwargs)

    return request_token_if_needed


class QSCloudClient:
    """A class representing a client to the backend."""

    _base_domain: str

    _email: str
    _password: str
    _token: Token | None
    _token_expires_at: datetime | None

    _api_base_url: str
    _fdsn_base_url: str

    def __init__(
        self: QSCloudClient,
        email: str,
        password: str,
        base_domain: str | None = "network.quakesaver.net",
    ) -> None:
        """Create an instance of the class.

        Args:
            email: The _email address used to authenticate at the backend.
            password: The _password used to authenticate at the backend.
            base_domain: The base domain for the remote connection.
        """
        self._email = email
        self._password = password
        self._token = None
        self._token_expires_at = None

        self._base_domain = base_domain

        self._api_base_url = f"https://api.{base_domain}/api/v1"
        self._fdsn_base_url = f"https://fdsnws.{base_domain}/fdsnws"

    def _token_needs_renewal(self: QSCloudClient) -> bool:
        """Check whether a new session token has to be requested.

        Returns:
            bool: True if there is no token yet, or the current one is about
                to expire.
        """
        if self._token is None or self._token_expires_at is None:
            return True
        deadline = self._token_expires_at - TOKEN_REFRESH_MARGIN
        return datetime.now(tz=timezone.utc) >= deadline

    @_needs_token
    def _get_authorization_headers(self: QSCloudClient) -> dict:
        return {"Authorization": f"{self._token.token_type} {self._token.access_token}"}

    def get_sensor_ids(self: QSCloudClient) -> list[str]:
        """Fetch all sensor UIDs the user has access to.

        Returns:
            list[str]: The list of sensor UIDs.
        """
        logging.debug("QSCloudClient requesting sensor ids.")
        response = requests.get(
            url=f"{self._api_base_url}/user/me/sensors",
            headers=self._get_authorization_headers(),
        )
        response_data = handle_response(response)
        return list(response_data.keys())

    def get_sensor(self: QSCloudClient, sensor_uid: str) -> CloudSensor:
        """Fetch sensor data.

        Args:
            sensor_uid: The UID to request data from.

        Returns:
            CloudSensor: A sensor model to work with.
        """
        logging.debug("QSCloudClient requesting sensor %s.", sensor_uid)
        response = requests.get(
            url=f"{self._api_base_url}/sensors/{sensor_uid}",
            headers=self._get_authorization_headers(),
        )
        response_data = handle_response(response)
        try:
            sensor = CloudSensor(
                api_base_url=self._api_base_url,
                fdsn_base_url=self._fdsn_base_url,
                client=self,
                **response_data,
            )
        except ValidationError as e:
            raise CorruptedDataError from e
        return sensor
