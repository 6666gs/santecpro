"""Base instrument class wrapping pyvisa communication."""

from __future__ import annotations

import logging

import pyvisa
from santecpro.exceptions import InstrumentConnectionError

_trace_logger = logging.getLogger("santecpro.trace")


class BaseInstrument:
    """Base class for all instrument drivers.

    Wraps a pyvisa ResourceManager and provides SCPI query/write/read
    methods. Subclasses add instrument-specific commands.
    """

    def __init__(self, resource_manager, trace: bool = False):
        self._rm = resource_manager
        self._resource = None
        self._trace = trace

    @property
    def is_connected(self) -> bool:
        return self._resource is not None

    def connect(
        self,
        resource_string: str,
        terminator: str = "\r",
        read_terminator: str | None = None,
    ) -> None:
        """Open a VISA resource and configure terminator."""
        if self._resource is not None:
            raise InstrumentConnectionError(
                f"Already connected. Disconnect first. Resource: {resource_string}"
            )
        try:
            self._resource = self._rm.open_resource(resource_string)
        except Exception as exc:
            raise InstrumentConnectionError(
                f"Failed to connect to {resource_string}: {exc}"
            ) from exc
        self._resource.write_termination = terminator
        self._resource.read_termination = read_terminator or terminator

    def disconnect(self) -> None:
        """Close the VISA resource."""
        if self._resource is not None:
            self._resource.close()
            self._resource = None

    def _require_connected(self) -> None:
        if self._resource is None:
            raise InstrumentConnectionError("Not connected. Call connect() first.")

    def query(self, command: str) -> str:
        """Send a SCPI query and return the response string."""
        self._require_connected()
        if self._trace:
            _trace_logger.debug("Q: %s", command)
        response = self._resource.query(command).strip()
        if self._trace:
            _trace_logger.debug("R: %s", response)
        return response

    def write(self, command: str) -> None:
        """Send a SCPI command (no response expected)."""
        self._require_connected()
        if self._trace:
            _trace_logger.debug("W: %s", command)
        self._resource.write(command)

    def read(self) -> str:
        """Read a response from the instrument."""
        self._require_connected()
        return self._resource.read()

    @property
    def idn(self) -> str:
        """Return the instrument identification string (*IDN?)."""
        return self.query("*IDN?")

    @property
    def timeout(self) -> int:
        """Return the VISA timeout in milliseconds."""
        self._require_connected()
        return self._resource.timeout

    @timeout.setter
    def timeout(self, value: int) -> None:
        self._require_connected()
        self._resource.timeout = value
