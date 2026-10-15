"""Tests for the gkphomepython client."""

from typing import Any
from unittest.mock import patch

import aiohttp
import pytest

from gkphomepython import (
    GkpAuth,
    GkpAuthError,
    GkpClient,
    GkpConnectionError,
    GkpDeviceError,
    GkpError,
    GkpMode,
    GkpRateLimitError,
    GkpTimeoutError,
    Installation,
    Thermostat,
)

from .common import ACCESS_TOKEN, USER_ID, FakeApi, load_fixture

INSTALLATIONS_PATH = f"/businessmodule/v1/installations/admins/{USER_ID}"
CONTENT_PATH = "/iotmanagement/v1/configuration/AABBCCDDEE01/AABBCCDDEE01/v1/content/"
CONTENT_PATH_2 = "/iotmanagement/v1/configuration/AABBCCDDEE02/AABBCCDDEE02/v1/content/"
CONFIG_PATH = "/iotmanagement/v1/devices/twin/properties/config/replace"
USER_CONNECTED_PATH = "/iotmanagement/v1/devices/userconnected"


def _configuration(data: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "Id_deviceId": "AABBCCDDEE01",
        "S1": "AABBCCDDEE01",
        "configurationVersion": "v1.0",
        "data": data,
    }


async def test_get_installations(client: GkpClient, fake_api: FakeApi) -> None:
    """Test fetching installations with auth headers."""
    fake_api.add("GET", INSTALLATIONS_PATH, load_fixture("installations.json"))

    installations = await client.get_installations()

    assert [i.installation_id for i in installations] == ["installation-1"]
    headers = fake_api.sent("GET", INSTALLATIONS_PATH)[0].headers
    assert headers["Authorization"] == f"Bearer {ACCESS_TOKEN}"
    assert headers["Ocp-Apim-Subscription-Key"] == "key"


async def test_get_installations_unexpected(
    client: GkpClient, fake_api: FakeApi
) -> None:
    """Test an unexpected installations payload."""
    fake_api.add("GET", INSTALLATIONS_PATH, {"error": "x"})

    with pytest.raises(GkpError):
        await client.get_installations()


async def test_get_thermostat(
    client: GkpClient, fake_api: FakeApi, installation: Installation
) -> None:
    """Test fetching a thermostat state."""
    fake_api.add("GET", CONTENT_PATH, load_fixture("device_content.json"))

    thermostat = await client.get_thermostat("AABBCCDDEE01", installation)

    assert thermostat.mode is GkpMode.COMFORT
    assert thermostat.current_temperature == 21.1


@pytest.mark.parametrize("body", [pytest.param("", id="empty"), pytest.param("[]", id="list")])
async def test_get_device_content_missing(
    client: GkpClient, fake_api: FakeApi, body: str
) -> None:
    """Test a device without configuration."""
    fake_api.add("GET", CONTENT_PATH, body=body)

    with pytest.raises(GkpDeviceError):
        await client.get_device_content("AABBCCDDEE01")


async def test_notify_user_connected(client: GkpClient, fake_api: FakeApi) -> None:
    """Test waking up the devices of an installation."""
    fake_api.add("PUT", USER_CONNECTED_PATH, ["AABBCCDDEE01"])

    await client.notify_user_connected("installation-1")

    assert fake_api.sent("PUT", USER_CONNECTED_PATH)[0].json == {
        "A1": USER_ID,
        "In": "installation-1",
    }


async def test_set_mode(client: GkpClient, fake_api: FakeApi) -> None:
    """Test setting the mode."""
    fake_api.add("PUT", CONFIG_PATH, {})

    await client.set_mode("AABBCCDDEE01", GkpMode.ECO)

    assert fake_api.sent("PUT", CONFIG_PATH)[0].json == _configuration(
        [{"wattsType": "Dm", "wattsTypeValue": 1}]
    )


@pytest.mark.parametrize(
    ("mode", "temperature", "expected"),
    [
        pytest.param(
            GkpMode.COMFORT,
            21.5,
            [{"wattsType": "Dm", "wattsTypeValue": 3}, {"wattsType": "cf", "wattsTypeValue": 707}],
            id="comfort",
        ),
        pytest.param(
            GkpMode.ECO,
            17.0,
            [{"wattsType": "Dm", "wattsTypeValue": 1}, {"wattsType": "ec", "wattsTypeValue": 626}],
            id="eco",
        ),
        pytest.param(
            GkpMode.BOOST,
            25.0,
            [{"wattsType": "Dm", "wattsTypeValue": 5}, {"wattsType": "bo", "wattsTypeValue": 770}],
            id="boost",
        ),
        pytest.param(
            GkpMode.AUTO,
            23.0,
            [{"wattsType": "Dm", "wattsTypeValue": 5}, {"wattsType": "bo", "wattsTypeValue": 734}],
            id="auto_starts_boost",
        ),
        pytest.param(
            GkpMode.COMFORT,
            35.0,
            [{"wattsType": "Dm", "wattsTypeValue": 3}, {"wattsType": "cf", "wattsTypeValue": 950}],
            id="max",
        ),
        pytest.param(
            GkpMode.ECO,
            5.0,
            [{"wattsType": "Dm", "wattsTypeValue": 1}, {"wattsType": "ec", "wattsTypeValue": 410}],
            id="min",
        ),
    ],
)
async def test_set_temperature(
    client: GkpClient,
    fake_api: FakeApi,
    mode: GkpMode,
    temperature: float,
    expected: list[dict[str, Any]],
) -> None:
    """Test setting the setpoint of the current mode."""
    fake_api.add("PUT", CONFIG_PATH, {})

    await client.set_temperature("AABBCCDDEE01", mode, temperature)

    assert fake_api.sent("PUT", CONFIG_PATH)[0].json == _configuration(expected)


@pytest.mark.parametrize(
    ("mode", "temperature"),
    [
        pytest.param(GkpMode.OFF, 20.0, id="off"),
        pytest.param(GkpMode.DEFROST, 7.0, id="defrost"),
        pytest.param(GkpMode.ECO, 35.5, id="too_high"),
        pytest.param(GkpMode.COMFORT, 4.5, id="too_low"),
        pytest.param(GkpMode.AUTO, 36.0, id="boost_too_high"),
    ],
)
async def test_set_temperature_rejected(
    client: GkpClient, fake_api: FakeApi, mode: GkpMode, temperature: float
) -> None:
    """Test invalid setpoint requests are rejected before any call."""
    with pytest.raises(GkpDeviceError):
        await client.set_temperature("AABBCCDDEE01", mode, temperature)

    assert not fake_api.requests


async def test_activate_boost_with_duration(
    client: GkpClient, fake_api: FakeApi
) -> None:
    """Test starting a boost with a duration."""
    fake_api.add("PUT", CONFIG_PATH, {})

    await client.activate_boost("AABBCCDDEE01", 24.0, 90)

    assert fake_api.sent("PUT", CONFIG_PATH)[0].json == _configuration(
        [
            {"wattsType": "Dm", "wattsTypeValue": 5},
            {"wattsType": "bo", "wattsTypeValue": 752},
            {"wattsType": "Bt", "wattsTypeValue": 90},
        ]
    )


@pytest.mark.parametrize("duration", [2, 1441])
async def test_activate_boost_invalid_duration(
    client: GkpClient, fake_api: FakeApi, duration: int
) -> None:
    """Test boost durations outside the firmware range."""
    with pytest.raises(GkpDeviceError):
        await client.activate_boost("AABBCCDDEE01", 24.0, duration)

    assert not fake_api.requests


async def test_retry_on_unauthorized(client: GkpClient, fake_api: FakeApi) -> None:
    """Test a 401 is retried once."""
    fake_api.add("GET", INSTALLATIONS_PATH, status=401)
    fake_api.add("GET", INSTALLATIONS_PATH, [])

    assert await client.get_installations() == []
    assert len(fake_api.sent("GET", INSTALLATIONS_PATH)) == 2


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        pytest.param({"status": 401}, GkpAuthError, id="unauthorized"),
        pytest.param({"status": 403}, GkpAuthError, id="forbidden"),
        pytest.param({"status": 404}, GkpDeviceError, id="not_found"),
        pytest.param({"status": 500}, GkpError, id="server_error"),
        pytest.param({"delay": 2}, GkpTimeoutError, id="timeout"),
        pytest.param({"body": "{not json"}, GkpError, id="invalid_json"),
    ],
)
async def test_request_errors(
    client: GkpClient,
    fake_api: FakeApi,
    kwargs: dict[str, Any],
    expected: type[Exception],
) -> None:
    """Test HTTP errors are mapped to library exceptions."""
    fake_api.add("GET", CONTENT_PATH, **kwargs)

    with pytest.raises(expected):
        await client.get_device_content("AABBCCDDEE01")


async def test_connection_error(
    auth: GkpAuth, session: aiohttp.ClientSession
) -> None:
    """Test an unreachable API."""
    client = GkpClient(auth, session, base_url="http://127.0.0.1:9", timeout=1)

    with pytest.raises(GkpConnectionError):
        await client.get_device_content("AABBCCDDEE01")


@pytest.mark.parametrize(
    ("status", "headers", "retry_after"),
    [
        pytest.param(429, {"Retry-After": "30"}, 30, id="seconds"),
        pytest.param(429, {}, 60, id="missing"),
        pytest.param(
            429,
            {"Retry-After": "Wed, 30 Sep 2026 15:00:00 GMT"},
            60,
            id="http_date",
        ),
        pytest.param(403, {"Retry-After": "3600"}, 3600, id="quota_exceeded"),
    ],
)
async def test_rate_limited(
    client: GkpClient,
    fake_api: FakeApi,
    status: int,
    headers: dict[str, str],
    retry_after: int,
) -> None:
    """Test a rate limit exposes the delay requested by the API, without retrying."""
    fake_api.add("GET", CONTENT_PATH, status=status, headers=headers)

    with pytest.raises(GkpRateLimitError) as err:
        await client.get_device_content("AABBCCDDEE01")

    assert err.value.retry_after == retry_after
    assert isinstance(err.value, GkpConnectionError)
    assert len(fake_api.sent("GET", CONTENT_PATH)) == 1


async def test_get_thermostats(
    client: GkpClient, fake_api: FakeApi, installation: Installation
) -> None:
    """Test all thermostats are read, with an error per failing device."""
    fake_api.add("GET", CONTENT_PATH, load_fixture("device_content.json"))
    fake_api.add("GET", CONTENT_PATH_2, status=404)

    result = await client.get_thermostats([installation])

    assert list(result.thermostats) == ["AABBCCDDEE01"]
    assert isinstance(result.thermostats["AABBCCDDEE01"], Thermostat)
    assert list(result.errors) == ["AABBCCDDEE02"]
    assert isinstance(result.errors["AABBCCDDEE02"], GkpDeviceError)


@pytest.mark.parametrize(
    ("status", "headers", "error"),
    [
        pytest.param(401, {}, GkpAuthError, id="auth"),
        pytest.param(429, {"Retry-After": "30"}, GkpRateLimitError, id="rate_limited"),
    ],
)
async def test_get_thermostats_account_error(
    client: GkpClient,
    fake_api: FakeApi,
    installation: Installation,
    status: int,
    headers: dict[str, str],
    error: type[GkpError],
) -> None:
    """Test errors affecting the whole account are raised."""
    fake_api.add("GET", CONTENT_PATH, load_fixture("device_content.json"))
    fake_api.add("GET", CONTENT_PATH_2, status=status, headers=headers)

    with pytest.raises(error):
        await client.get_thermostats([installation])


async def test_get_thermostats_unexpected_error(
    client: GkpClient, installation: Installation
) -> None:
    """Test unexpected errors are raised instead of returned."""
    with (
        patch.object(client, "get_thermostat", side_effect=ValueError("bug")),
        pytest.raises(ValueError),
    ):
        await client.get_thermostats([installation])
