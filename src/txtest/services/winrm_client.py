from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

from txtest.services.error_mapper import WinRMTransportError


@dataclass(slots=True)
class WinRMExecutionResult:
    stdout: str
    stderr: str
    exit_code: int


class WinRMClientProtocol(Protocol):
    async def run_script(self, host: str, script_path: str, parameters: dict, timeout_seconds: int) -> WinRMExecutionResult: ...


class MockWinRMClient:
    def __init__(self, responses: dict[str, WinRMExecutionResult] | None = None) -> None:
        self.responses = responses or {}

    async def run_script(self, host: str, script_path: str, parameters: dict, timeout_seconds: int) -> WinRMExecutionResult:
        await asyncio.sleep(0)
        key = f"{host}:{script_path}"
        if key not in self.responses:
            raise WinRMTransportError(f"No mock response defined for {key}")
        return self.responses[key]
