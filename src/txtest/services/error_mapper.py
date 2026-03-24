from __future__ import annotations

from dataclasses import dataclass

from txtest.models.domain import DomainStatus


class WinRMTransportError(Exception):
    pass


class WinRMAuthError(Exception):
    pass


class WinRMUnreachableError(Exception):
    pass


@dataclass(slots=True)
class ErrorMapper:
    def map_exception(self, exc: Exception) -> DomainStatus:
        if isinstance(exc, TimeoutError):
            return DomainStatus.TIMEOUT
        if isinstance(exc, WinRMAuthError):
            return DomainStatus.AUTH_FAILED
        if isinstance(exc, WinRMUnreachableError):
            return DomainStatus.UNREACHABLE
        if isinstance(exc, ValueError):
            return DomainStatus.INVALID_OUTPUT
        if isinstance(exc, WinRMTransportError):
            return DomainStatus.ERROR
        return DomainStatus.ERROR

    def is_transient(self, exc: Exception) -> bool:
        return isinstance(exc, (TimeoutError, ConnectionError, WinRMTransportError, WinRMUnreachableError))
