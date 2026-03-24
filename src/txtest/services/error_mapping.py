from __future__ import annotations

import json

from txtest.models import DomainStatus, ScriptExecutionResult


class WinRMConnectionError(Exception):
    pass


class WinRMAuthError(Exception):
    pass


class WinRMExecutionTimeout(Exception):
    pass


class InvalidScriptOutputError(Exception):
    pass


def map_exception_to_status(exc: Exception) -> DomainStatus:
    if isinstance(exc, WinRMAuthError):
        return DomainStatus.AUTH_FAILED
    if isinstance(exc, WinRMExecutionTimeout):
        return DomainStatus.TIMEOUT
    if isinstance(exc, WinRMConnectionError):
        return DomainStatus.UNREACHABLE
    if isinstance(exc, InvalidScriptOutputError):
        return DomainStatus.INVALID_OUTPUT
    return DomainStatus.ERROR


def parse_script_stdout(stdout: str) -> ScriptExecutionResult:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise InvalidScriptOutputError("Script stdout is not valid JSON") from exc
    try:
        return ScriptExecutionResult.model_validate(payload)
    except Exception as exc:
        raise InvalidScriptOutputError(f"Script JSON failed schema validation: {exc}") from exc
