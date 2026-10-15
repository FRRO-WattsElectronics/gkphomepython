"""Main client for the GKP API."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from http import HTTPStatus
import json
import logging
from typing import Any

import aiohttp

from .auth import GkpAuth
from .const import (
    API_BASE_URL,
    API_ENDPOINTS,
    API_TIMEOUT,
    APIM_SUBSCRIPTION_KEY,
    BOOST_DURATION_MAX,
    BOOST_DURATION_MIN,
    CONFIGURATION_VERSION,
    DEFAULT_RETRY_AFTER,
    MAX_PARALLEL_REQUESTS,
    MODE_SETPOINT_KEY,
    SETPOINT_MAX,
    SETPOINT_MIN,
    GkpMode,
)
from .exceptions import (
    GkpAuthError,
    GkpConnectionError,
    GkpDeviceError,
    GkpError,
    GkpRateLimitError,
    GkpTimeoutError,
)
from .models import Installation, Thermostat, celsius_to_deci_fahrenheit

_LOGGER = logging.getLogger(__name__)


class GkpClient:
    """Client for the GKP API."""

    def __init__(
        self,
        auth: GkpAuth,
        session: aiohttp.ClientSession,
        *,
        base_url: str = API_BASE_URL,
        subscription_key: str = APIM_SUBSCRIPTION_KEY,
        timeout: float = API_TIMEOUT,
    ) -> None:
        """Initialize the client."""
        self.auth = auth
        self._session = session
        self._base_url = base_url
        self._subscription_key = subscription_key
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def _request(
        self,
        method: str,
        endpoint: str,
        json_data: Any = None,
    ) -> Any:
        """Send one authenticated request and return the decoded body."""
        token = await self.auth.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Ocp-Apim-Subscription-Key": self._subscription_key,
        }
        async with self._session.request(
            method,
            f"{self._base_url}{endpoint}",
            headers=headers,
            json=json_data,
            timeout=self._timeout,
        ) as response:
            response.raise_for_status()
            body = await response.text()
        return json.loads(body) if body else None

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: Any = None,
    ) -> Any:
        """Make an authenticated request, retrying once on 401."""
        try:
            try:
                return await self._request(method, endpoint, json_data)
            except aiohttp.ClientResponseError as err:
                if err.status != HTTPStatus.UNAUTHORIZED:
                    raise
                return await self._request(method, endpoint, json_data)
        except TimeoutError as err:
            raise GkpTimeoutError(
                f"Request timed out after {self._timeout.total}s"
            ) from err
        except aiohttp.ClientResponseError as err:
            if err.status == HTTPStatus.TOO_MANY_REQUESTS or (
                # APIM answers an exceeded quota with a 403 and a Retry-After
                err.status == HTTPStatus.FORBIDDEN
                and "Retry-After" in (err.headers or {})
            ):
                retry_after = _parse_retry_after(err.headers)
                raise GkpRateLimitError(
                    f"Rate limited, retry after {retry_after}s", retry_after
                ) from err
            if err.status in (HTTPStatus.UNAUTHORIZED, HTTPStatus.FORBIDDEN):
                raise GkpAuthError(f"Access denied: {err}") from err
            if err.status == HTTPStatus.NOT_FOUND:
                raise GkpDeviceError(f"Resource not found: {endpoint}") from err
            raise GkpError(f"API request failed: {err}") from err
        except aiohttp.ClientError as err:
            raise GkpConnectionError(f"Connection error: {err}") from err
        except ValueError as err:
            raise GkpError(f"Invalid response for {endpoint}: {err}") from err

    async def get_installations(self) -> list[Installation]:
        """Get the installations where the user is the main administrator."""
        user_id = await self.auth.get_user_id()
        data = await self._make_request(
            "GET", API_ENDPOINTS["installations"].format(user_id=user_id)
        )
        if not isinstance(data, list):
            raise GkpError("Unexpected installations response")

        installations = [Installation.from_dict(item) for item in data]
        _LOGGER.debug("Found %d installations", len(installations))
        return installations

    async def get_device_content(self, device_id: str) -> dict[str, Any]:
        """Get the raw configuration content of a device."""
        data = await self._make_request(
            "GET", API_ENDPOINTS["device_content"].format(device_id=device_id)
        )
        if not isinstance(data, dict):
            raise GkpDeviceError(f"No configuration found for device {device_id}")
        return data

    async def get_thermostat(
        self, device_id: str, installation: Installation
    ) -> Thermostat:
        """Get the current state of a thermostat."""
        content = await self.get_device_content(device_id)
        return Thermostat.from_content(device_id, installation, content)

    async def get_thermostats(
        self, installations: Iterable[Installation]
    ) -> dict[str, Thermostat | GkpError]:
        """Get the state of every thermostat of the installations.

        Errors are returned per device, so a failing device does not hide the
        others. Unexpected errors are raised.
        """
        devices = [
            (device_id, installation)
            for installation in installations
            for device_id in installation.device_ids
        ]
        semaphore = asyncio.Semaphore(MAX_PARALLEL_REQUESTS)

        async def fetch(device_id: str, installation: Installation) -> Thermostat:
            async with semaphore:
                return await self.get_thermostat(device_id, installation)

        results = await asyncio.gather(
            *(fetch(device_id, installation) for device_id, installation in devices),
            return_exceptions=True,
        )

        thermostats: dict[str, Thermostat | GkpError] = {}
        for (device_id, _), result in zip(devices, results, strict=True):
            if not isinstance(result, Thermostat | GkpError):
                raise result
            thermostats[device_id] = result
        return thermostats

    async def notify_user_connected(self, installation_id: str) -> None:
        """Ask all devices of an installation to report their current state."""
        user_id = await self.auth.get_user_id()
        await self._make_request(
            "PUT",
            API_ENDPOINTS["user_connected"],
            {"A1": user_id, "In": installation_id},
        )
        _LOGGER.debug("Sent user connected to installation %s", installation_id)

    async def _send_configuration(
        self, device_id: str, data: list[dict[str, Any]]
    ) -> None:
        """Send new configuration values to a device."""
        await self._make_request(
            "PUT",
            API_ENDPOINTS["set_configuration"],
            {
                "Id_deviceId": device_id,
                "S1": device_id,
                "configurationVersion": CONFIGURATION_VERSION,
                "data": data,
            },
        )

    async def set_mode(self, device_id: str, mode: GkpMode) -> None:
        """Set the thermostat mode."""
        await self._send_configuration(
            device_id, [{"wattsType": "Dm", "wattsTypeValue": int(mode)}]
        )
        _LOGGER.debug("Set mode %s for device %s", mode.name, device_id)

    async def set_temperature(
        self, device_id: str, current_mode: GkpMode, temperature: float
    ) -> None:
        """Set the setpoint of the current mode.

        In AUTO mode the program drives the setpoint, so a boost is started
        at the requested temperature instead.
        """
        if current_mode is GkpMode.AUTO:
            await self.activate_boost(device_id, temperature)
            return
        if current_mode not in (GkpMode.ECO, GkpMode.COMFORT, GkpMode.BOOST):
            raise GkpDeviceError(
                f"Setpoint cannot be changed in {current_mode.name} mode"
            )

        _validate_setpoint(temperature)
        await self._send_configuration(
            device_id,
            [
                {"wattsType": "Dm", "wattsTypeValue": int(current_mode)},
                {
                    "wattsType": MODE_SETPOINT_KEY[current_mode],
                    "wattsTypeValue": celsius_to_deci_fahrenheit(temperature),
                },
            ],
        )
        _LOGGER.debug(
            "Set %s setpoint to %s°C for device %s",
            current_mode.name,
            temperature,
            device_id,
        )

    async def activate_boost(
        self,
        device_id: str,
        temperature: float,
        duration_minutes: int | None = None,
    ) -> None:
        """Start boost mode at a temperature, optionally for a duration."""
        _validate_setpoint(temperature)
        data: list[dict[str, Any]] = [
            {"wattsType": "Dm", "wattsTypeValue": int(GkpMode.BOOST)},
            {
                "wattsType": MODE_SETPOINT_KEY[GkpMode.BOOST],
                "wattsTypeValue": celsius_to_deci_fahrenheit(temperature),
            },
        ]
        if duration_minutes is not None:
            if not BOOST_DURATION_MIN <= duration_minutes <= BOOST_DURATION_MAX:
                raise GkpDeviceError(
                    f"Boost duration {duration_minutes} is outside allowed range "
                    f"({BOOST_DURATION_MIN}-{BOOST_DURATION_MAX} min)"
                )
            data.append({"wattsType": "Bt", "wattsTypeValue": duration_minutes})

        await self._send_configuration(device_id, data)
        _LOGGER.debug(
            "Activated boost at %s°C for device %s (duration %s)",
            temperature,
            device_id,
            duration_minutes,
        )


def _parse_retry_after(headers: Mapping[str, str] | None) -> int:
    """Return the Retry-After delay in seconds, or a default one."""
    try:
        return int((headers or {}).get("Retry-After", ""))
    except ValueError:
        return DEFAULT_RETRY_AFTER


def _validate_setpoint(temperature: float) -> None:
    """Raise if the temperature is outside the range allowed by the application."""
    if not SETPOINT_MIN <= temperature <= SETPOINT_MAX:
        raise GkpDeviceError(
            f"Temperature {temperature} is outside allowed range "
            f"({SETPOINT_MIN}-{SETPOINT_MAX})"
        )
