"""Data models for the GKP API."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from .const import (
    DEFAULT_LOCATION,
    DEVICE_DATE_FORMAT,
    FIRST_REPORT_TIMEOUT,
    LOCATION_TIMEZONES,
    OFFLINE_AFTER,
    TEMP_ERR,
    GkpMode,
)


def deci_fahrenheit_to_celsius(value: int) -> float | None:
    """Convert a firmware temperature (1/10 °F) to °C."""
    if value == TEMP_ERR:
        return None
    return round((value - 320) * 5 / 90, 1)


def celsius_to_deci_fahrenheit(value: float) -> int:
    """Convert a temperature in °C to the firmware unit (1/10 °F)."""
    return round(value * 18 + 320)


def _as_int(value: Any) -> int | None:
    """Parse an integer value, the API returns numbers or strings."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _parse_device_date(value: Any, location: Any) -> datetime | None:
    """Parse the device local date (Dd) into an aware datetime."""
    if not isinstance(value, str):
        return None
    try:
        naive = datetime.strptime(value.strip(), DEVICE_DATE_FORMAT)
    except ValueError:
        return None
    timezone = LOCATION_TIMEZONES.get(
        str(location).strip().upper() if location else DEFAULT_LOCATION,
        LOCATION_TIMEZONES[DEFAULT_LOCATION],
    )
    return naive.replace(tzinfo=ZoneInfo(timezone))


def _latest_timestamp(content: dict[str, Any]) -> datetime | None:
    """Return the most recent UTC timestamp attached to the stored values."""
    timestamps = [
        timestamp
        for entry in content.values()
        if isinstance(entry, dict)
        and (timestamp := _as_int(entry.get("timestamp"))) is not None
        and timestamp > 0
    ]
    if not timestamps:
        return None
    latest = max(timestamps)
    # Tolerate timestamps stored in milliseconds
    if latest > 10**11:
        latest //= 1000
    return datetime.fromtimestamp(latest, UTC)


@dataclass
class Installation:
    """Installation owned by the user, with one thermostat per room."""

    installation_id: str
    name: str
    rooms: dict[str, str] = field(default_factory=dict)
    """Room name by device ID."""

    @property
    def device_ids(self) -> list[str]:
        """Return the IDs of the devices of the installation."""
        return list(self.rooms)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Installation:
        """Create an installation from API response data."""
        rooms: dict[str, str] = {}
        for room in data.get("rooms") or []:
            devices = room.get("devices") or []
            if not devices or not (device_id := devices[0].get("Id_deviceId")):
                continue
            rooms[str(device_id)] = str(room.get("Rn") or device_id)
        return cls(
            installation_id=str(data["id"]),
            name=str(data.get("Il") or data["id"]),
            rooms=rooms,
        )


@dataclass
class Thermostat:
    """GKP Wi-Fi radiator."""

    device_id: str
    installation_id: str
    installation_name: str
    room_name: str
    mode: GkpMode | None = None
    current_temperature: float | None = None
    setpoint: float | None = None
    eco_setpoint: float | None = None
    comfort_setpoint: float | None = None
    defrost_setpoint: float | None = None
    boost_setpoint: float | None = None
    boost_remaining_minutes: int | None = None
    is_heating: bool = False
    device_date: datetime | None = None
    last_update: datetime | None = None
    firmware_version: str | None = None
    device_type: str | None = None

    def is_online(self, now: datetime, first_wake_up: datetime | None = None) -> bool:
        """Return True if the device reported recently or may not have answered yet.

        first_wake_up is when the caller first woke up the devices, if it did.
        """
        if self.last_update is not None and now - self.last_update <= OFFLINE_AFTER:
            return True
        return first_wake_up is not None and now - first_wake_up < FIRST_REPORT_TIMEOUT

    @classmethod
    def from_content(
        cls,
        device_id: str,
        installation: Installation,
        content: dict[str, Any],
    ) -> Thermostat:
        """Create a thermostat from the device configuration content."""

        def value(watts_type: str) -> Any:
            entry = content.get(watts_type)
            return entry.get("value") if isinstance(entry, dict) else None

        def temperature(watts_type: str) -> float | None:
            raw = _as_int(value(watts_type))
            return None if raw is None else deci_fahrenheit_to_celsius(raw)

        mode: GkpMode | None = None
        if (raw_mode := _as_int(value("Cm"))) is not None:
            with suppress(ValueError):
                mode = GkpMode(raw_mode)
        device_date = _parse_device_date(value("Dd"), value("Lo"))
        firmware_version = value("Sv")
        device_type = value("Ty")

        return cls(
            device_id=device_id,
            installation_id=installation.installation_id,
            installation_name=installation.name,
            room_name=installation.rooms.get(device_id, device_id),
            mode=mode,
            current_temperature=temperature("At"),
            setpoint=None if mode is GkpMode.OFF else temperature("Sp"),
            eco_setpoint=temperature("ec"),
            comfort_setpoint=temperature("cf"),
            defrost_setpoint=temperature("df"),
            boost_setpoint=temperature("bo"),
            boost_remaining_minutes=_as_int(value("Bt")),
            is_heating=_as_int(value("Hs")) == 1,
            device_date=device_date,
            last_update=_latest_timestamp(content) or device_date,
            firmware_version=str(firmware_version) if firmware_version else None,
            device_type=str(device_type) if device_type else None,
        )
