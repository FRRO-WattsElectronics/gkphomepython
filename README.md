# gkphomepython

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A Python API wrapper for GKP Wi-Fi radiators, providing easy Home Assistant integration with the GKP cloud.

## Features

- **OAuth2 authentication** - Secure token-based authentication with automatic refresh
- **Installation discovery** - Discovery of the installations where the user is the main administrator
- **Thermostat control** - Set temperature and modes, and read the current status
- **Device wake up** - Ask the radiators to report their current state
- **Rate limiting** - Expose the delay requested by the API when it rate limits the user

## Installation

### From source

```bash
pip install .
```

## Usage

```python
from gkphomepython import GkpAuth, GkpClient, GkpMode

auth = GkpAuth(oauth_session)  # object exposing `token` and `async_ensure_token_valid()`
client = GkpClient(auth, aiohttp_session)

installations = await client.get_installations()
for installation in installations:
    await client.notify_user_connected(installation.installation_id)

thermostats = await client.get_thermostats(installations)

await client.set_mode(device_id, GkpMode.COMFORT)
await client.set_temperature(device_id, GkpMode.COMFORT, 21.5)
```

## Supported Device Types

### Thermostat
Control and monitor GKP Wi-Fi radiators.

**Available thermostat modes:**
- `OFF` - Turn off heating
- `ECO` - Energy saving mode
- `AUTO` - Follow programmed schedule
- `COMFORT` - Comfort mode
- `DEFROST` - Frost protection mode
- `BOOST` - Boost mode for a limited duration

Temperatures are exposed in °C; the firmware unit (1/10 °F) is converted by the
library. Setting a temperature in `AUTO` mode starts a boost.

## Requirements

- Python 3.12+
- aiohttp >= 3.8.0

## Development

```bash
uv venv .venv && uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/python -m pytest --cov=gkphomepython
.venv/bin/python -m mypy gkphomepython
.venv/bin/python -m build
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Changelog

### 0.2.0 (2026-10-01)
- Add `get_thermostats` to read every thermostat of the installations
- Move the online detection and the firmware timings to the library
- Always provide a delay when the API rate limits the user
- Add `GkpRateLimitError`
- Use the Home Assistant APIM subscription key

### 0.1.0 (2026-09-30)
- Initial release
- OAuth2 authentication support
- Installation discovery and thermostat control
