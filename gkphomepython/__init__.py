"""Python API wrapper for GKP Wi-Fi radiators."""

from .auth import GkpAuth
from .client import GkpClient
from .const import (
    BOOST_DURATION_MAX,
    BOOST_DURATION_MIN,
    SETPOINT_MAX,
    SETPOINT_MIN,
    USER_CONNECTED_INTERVAL,
    USER_CONNECTED_REPORT_DELAY,
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
from .models import Installation, Thermostat, ThermostatsResult

__version__ = "0.3.0"

__all__ = [
    "BOOST_DURATION_MAX",
    "BOOST_DURATION_MIN",
    "SETPOINT_MAX",
    "SETPOINT_MIN",
    "USER_CONNECTED_INTERVAL",
    "USER_CONNECTED_REPORT_DELAY",
    "GkpAuth",
    "GkpAuthError",
    "GkpClient",
    "GkpConnectionError",
    "GkpDeviceError",
    "GkpError",
    "GkpMode",
    "GkpRateLimitError",
    "GkpTimeoutError",
    "Installation",
    "Thermostat",
    "ThermostatsResult",
]
