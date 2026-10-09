"""Exceptions for the GKP API."""


class GkpError(Exception):
    """Base exception for the GKP API."""


class GkpAuthError(GkpError):
    """Authentication error."""


class GkpConnectionError(GkpError):
    """Connection error."""


class GkpDeviceError(GkpError):
    """Device operation error."""


class GkpTimeoutError(GkpError):
    """Request timeout error."""


class GkpRateLimitError(GkpConnectionError):
    """Too many requests for the user."""

    def __init__(self, message: str, retry_after: int) -> None:
        """Initialize the error with the delay requested by the API, in seconds."""
        super().__init__(message)
        self.retry_after = retry_after
