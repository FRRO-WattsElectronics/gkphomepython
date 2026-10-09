"""Tests for gkphomepython models."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from gkphomepython import GkpMode, Installation, Thermostat
from gkphomepython.models import (
    celsius_to_deci_fahrenheit,
    deci_fahrenheit_to_celsius,
)

from .common import load_fixture


@pytest.mark.parametrize(
    ("deci_fahrenheit", "celsius"),
    [(320, 0.0), (464, 8.0), (680, 20.0), (689, 20.5), (716, 22.0), (860, 30.0)],
)
def test_temperature_conversion(deci_fahrenheit: int, celsius: float) -> None:
    """Test conversions both ways between 1/10 °F and °C."""
    assert deci_fahrenheit_to_celsius(deci_fahrenheit) == celsius
    assert celsius_to_deci_fahrenheit(celsius) == deci_fahrenheit


def test_temperature_error_value() -> None:
    """Test the firmware error value is converted to None."""
    assert deci_fahrenheit_to_celsius(0x7FFF) is None


def test_installation_from_dict() -> None:
    """Test parsing an installation skips rooms without device."""
    installation = Installation.from_dict(load_fixture("installations.json")[0])

    assert installation.installation_id == "installation-1"
    assert installation.name == "Maison"
    assert installation.rooms == {"AABBCCDDEE01": "Salon", "AABBCCDDEE02": "Chambre"}
    assert installation.device_ids == ["AABBCCDDEE01", "AABBCCDDEE02"]


def test_installation_without_label() -> None:
    """Test the installation ID is used when there is no label."""
    installation = Installation.from_dict({"id": "installation-2", "rooms": None})

    assert installation.name == "installation-2"
    assert installation.rooms == {}


def test_thermostat_from_content(installation: Installation) -> None:
    """Test parsing a thermostat from the device content."""
    thermostat = Thermostat.from_content(
        "AABBCCDDEE01", installation, load_fixture("device_content.json")
    )

    assert thermostat.room_name == "Salon"
    assert thermostat.installation_name == "Maison"
    assert thermostat.mode is GkpMode.COMFORT
    assert thermostat.current_temperature == 21.1
    assert thermostat.setpoint == 22.0
    assert thermostat.eco_setpoint == 18.0
    assert thermostat.comfort_setpoint == 22.0
    assert thermostat.defrost_setpoint == 8.0
    assert thermostat.boost_setpoint == 24.0
    assert thermostat.boost_remaining_minutes == 120
    assert thermostat.is_heating is True
    assert thermostat.firmware_version == "v01.04.00"
    assert thermostat.device_type == "P08073"
    # 14:05:07 in Paris (CEST) is 12:05:07 UTC
    assert thermostat.device_date == datetime(2026, 9, 30, 12, 5, 7, tzinfo=UTC)
    assert thermostat.last_update == thermostat.device_date


@pytest.mark.parametrize(
    ("location", "expected_utc_hour"),
    [("LONDON", 13), ("ATHENS", 11), ("MOSCOW", 11), ("UTC+0", 14), ("UNKNOWN", 12)],
)
def test_device_date_time_zone(
    installation: Installation, location: str, expected_utc_hour: int
) -> None:
    """Test the device date is interpreted in the device time zone."""
    content = load_fixture("device_content.json")
    content["Lo"]["value"] = location

    thermostat = Thermostat.from_content("AABBCCDDEE01", installation, content)

    assert thermostat.device_date is not None
    assert thermostat.device_date.astimezone(UTC).hour == expected_utc_hour


@pytest.mark.parametrize(
    "timestamp",
    [pytest.param(1790000000, id="seconds"), pytest.param(1790000000000, id="ms")],
)
def test_last_update_from_timestamps(
    installation: Installation, timestamp: int
) -> None:
    """Test stored UTC timestamps take precedence over the device date."""
    content = load_fixture("device_content.json")
    content["At"]["timestamp"] = timestamp
    content["Sp"]["timestamp"] = 1000

    thermostat = Thermostat.from_content("AABBCCDDEE01", installation, content)

    assert thermostat.last_update == datetime.fromtimestamp(1790000000, UTC)


@pytest.mark.parametrize(
    ("overrides", "attribute", "expected"),
    [
        pytest.param({"Cm": 0, "Sp": "32767"}, "setpoint", None, id="off_setpoint"),
        pytest.param({"Cm": 9}, "mode", None, id="unknown_mode"),
        pytest.param({"Cm": "abc"}, "mode", None, id="invalid_mode"),
        pytest.param({"At": 32767}, "current_temperature", None, id="sensor_error"),
        pytest.param({"Hs": 0}, "is_heating", False, id="not_heating"),
        pytest.param({"Dd": "garbage"}, "device_date", None, id="invalid_date"),
        pytest.param({"Dd": None}, "last_update", None, id="no_date"),
        pytest.param({"Sv": ""}, "firmware_version", None, id="no_firmware"),
        pytest.param({"Bt": True}, "boost_remaining_minutes", None, id="bool_value"),
    ],
)
def test_thermostat_edge_values(
    installation: Installation,
    overrides: dict[str, Any],
    attribute: str,
    expected: Any,
) -> None:
    """Test missing or invalid values are tolerated."""
    content = load_fixture("device_content.json")
    for key, value in overrides.items():
        content[key]["value"] = value

    thermostat = Thermostat.from_content("AABBCCDDEE01", installation, content)

    assert getattr(thermostat, attribute) == expected


def test_thermostat_empty_content(installation: Installation) -> None:
    """Test a device without stored configuration."""
    thermostat = Thermostat.from_content("UNKNOWN", installation, {"At": "bad"})

    assert thermostat.room_name == "UNKNOWN"
    assert thermostat.mode is None
    assert thermostat.current_temperature is None
    assert thermostat.last_update is None


@pytest.mark.parametrize(
    ("age", "first_wake_up_age", "online"),
    [
        pytest.param(timedelta(minutes=5), None, True, id="recent"),
        pytest.param(timedelta(minutes=30), None, True, id="limit"),
        pytest.param(timedelta(minutes=31), None, False, id="stale"),
        pytest.param(
            timedelta(hours=4), timedelta(minutes=1), True, id="awaiting_answer"
        ),
        pytest.param(
            timedelta(hours=4), timedelta(minutes=2), False, id="never_answered"
        ),
    ],
)
def test_is_online(
    installation: Installation,
    age: timedelta,
    first_wake_up_age: timedelta | None,
    online: bool,
) -> None:
    """Test online detection from the last update and the first wake up."""
    thermostat = Thermostat.from_content(
        "AABBCCDDEE01", installation, load_fixture("device_content.json")
    )
    assert thermostat.last_update is not None
    now = thermostat.last_update + age
    first_wake_up = None if first_wake_up_age is None else now - first_wake_up_age

    assert thermostat.is_online(now, first_wake_up) is online


def test_is_online_without_update(installation: Installation) -> None:
    """Test a device that never reported is offline."""
    thermostat = Thermostat.from_content("AABBCCDDEE01", installation, {})

    assert not thermostat.is_online(datetime.now(UTC))
