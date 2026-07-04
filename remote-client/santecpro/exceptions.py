"""Custom exceptions for santecpro."""


class SantecError(Exception):
    """Base exception for all santecpro errors."""

    def __init__(self, message: str, error_code: int | None = None):
        self.error_code = error_code
        super().__init__(message)


class InstrumentConnectionError(SantecError):
    """Raised when an instrument connection fails."""
    pass


class InstrumentOperationError(SantecError):
    """Raised when an instrument operation fails."""
    pass
