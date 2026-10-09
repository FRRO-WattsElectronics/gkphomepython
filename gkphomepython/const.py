"""Constants for the GKP API."""

from datetime import timedelta
from enum import IntEnum

# API configuration
API_BASE_URL = "https://gkp-apim-prd.azure-api.net"
# Subscription key of the Home Assistant APIM product, rate limited per user
APIM_SUBSCRIPTION_KEY = "3398016a681e4443ad067f8c8ea1312a"
API_TIMEOUT = 20

API_ENDPOINTS = {
    "installations": "/businessmodule/v1/installations/admins/{user_id}",
    "device_content": "/iotmanagement/v1/configuration/{device_id}/{device_id}/v1/content/",
    "set_configuration": "/iotmanagement/v1/devices/twin/properties/config/replace",
    "user_connected": "/iotmanagement/v1/devices/userconnected",
}

CONFIGURATION_VERSION = "v1.0"

# The devices only report their state when woken up through "user connected"
USER_CONNECTED_INTERVAL = timedelta(minutes=10)
# The devices report about a second after being woken up
USER_CONNECTED_REPORT_DELAY = timedelta(seconds=5)
# A device that missed three wake ups is offline
OFFLINE_AFTER = 3 * USER_CONNECTED_INTERVAL
# Devices are not judged offline before the first wake up had time to be answered
FIRST_REPORT_TIMEOUT = timedelta(minutes=2)

# Used when the API rate limits without a usable Retry-After header, in seconds
DEFAULT_RETRY_AFTER = 60
MAX_PARALLEL_REQUESTS = 5

# Value sent by the firmware when a temperature is not available
TEMP_ERR = 0x7FFF


class GkpMode(IntEnum):
    """Thermostat modes, as defined by the firmware."""

    OFF = 0
    ECO = 1
    AUTO = 2
    COMFORT = 3
    DEFROST = 4
    BOOST = 5


# Watts types holding the setpoint of each mode
MODE_SETPOINT_KEY: dict[GkpMode, str] = {
    GkpMode.ECO: "ec",
    GkpMode.COMFORT: "cf",
    GkpMode.DEFROST: "df",
    GkpMode.BOOST: "bo",
}

# Setpoint range in °C allowed by the GKP application, in every mode
SETPOINT_MIN = 5.0
SETPOINT_MAX = 35.0

BOOST_DURATION_MIN = 3
BOOST_DURATION_MAX = 1440

# Firmware time zone locations (Lo) to IANA time zones
LOCATION_TIMEZONES: dict[str, str] = {
    "PARIS": "Europe/Paris",
    "LONDON": "Europe/London",
    "ATHENS": "Europe/Athens",
    "MOSCOW": "Europe/Moscow",
    "UTC+0": "UTC",
}
DEFAULT_LOCATION = "PARIS"

DEVICE_DATE_FORMAT = "%d/%m/%Y %H:%M:%S"
