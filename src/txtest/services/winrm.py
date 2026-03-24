from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from txtest.services.credentials import WinRMCredentials

import requests
from spnego.exceptions import SpnegoError
from pypsrp.client import Client
from pypsrp.exceptions import AuthenticationError, WinRMError, WinRMTransportError
from pypsrp.powershell import PowerShell, RunspacePool

from txtest.models.core import TransportResult
from txtest.services.error_mapper import WinRMAuthError, WinRMTransportError as DomainTransportError, WinRMUnreachableError


class Transport(Protocol):
    async def run_script(
        self,
        hostname: str,
        script_path: Path,
        parameters: dict[str, Any],
        connect_timeout_seconds: int,
        execution_timeout_seconds: int,
        auth: str,
        credentials: WinRMCredentials | None = None,
    ) -> TransportResult: ...


@dataclass(slots=True)
class WinRMConnectionSettings:
    username: str | None = None
    password: str | None = None
    ssl: bool = False
    port: int | None = None
    path: str = "wsman"
    cert_validation: bool = False

    @classmethod
    def from_env(cls) -> "WinRMConnectionSettings":
        port_value = os.getenv("TXTTEST_WINRM_PORT")
        return cls(
            username=os.getenv("TXTTEST_WINRM_USERNAME") or None,
            password=os.getenv("TXTTEST_WINRM_PASSWORD") or None,
            ssl=os.getenv("TXTTEST_WINRM_USE_SSL", "false").lower() in {"1", "true", "yes", "on"},
            port=int(port_value) if port_value else None,
            path=os.getenv("TXTTEST_WINRM_PATH", "wsman"),
            cert_validation=os.getenv("TXTTEST_WINRM_CERT_VALIDATION", "false").lower() in {"1", "true", "yes", "on"},
        )


class MockTransport:
    def __init__(self, responses: dict[str, TransportResult] | None = None) -> None:
        self.responses = responses or {}

    async def run_script(
        self,
        hostname: str,
        script_path: Path,
        parameters: dict[str, Any],
        connect_timeout_seconds: int,
        execution_timeout_seconds: int,
        auth: str,
        credentials: WinRMCredentials | None = None,
    ) -> TransportResult:
        await asyncio.sleep(0)
        key = f"{hostname}:{script_path.name}"
        if key not in self.responses:
            raise DomainTransportError(f"No mock response defined for {key}")
        return self.responses[key]


class PypsrpTransport:
    def __init__(self, settings: WinRMConnectionSettings | None = None) -> None:
        self.settings = settings or WinRMConnectionSettings.from_env()

    async def run_script(
        self,
        hostname: str,
        script_path: Path,
        parameters: dict[str, Any],
        connect_timeout_seconds: int,
        execution_timeout_seconds: int,
        auth: str,
        credentials: WinRMCredentials | None = None,
    ) -> TransportResult:
        script_text = script_path.read_text(encoding="utf-8-sig")
        return await asyncio.to_thread(
            self._execute_script,
            hostname,
            script_text,
            parameters,
            connect_timeout_seconds,
            execution_timeout_seconds,
            auth,
            credentials,
        )

    def _execute_script(
        self,
        hostname: str,
        script_text: str,
        parameters: dict[str, Any],
        connect_timeout_seconds: int,
        execution_timeout_seconds: int,
        auth: str,
        credentials: WinRMCredentials | None = None,
    ) -> TransportResult:
        username = credentials.username if credentials is not None else self.settings.username
        password = credentials.password if credentials is not None else self.settings.password
        client = Client(
            hostname,
            username=username,
            password=password,
            ssl=self.settings.ssl,
            port=self.settings.port,
            path=self.settings.path,
            auth=auth,
            cert_validation=self.settings.cert_validation,
            connection_timeout=connect_timeout_seconds,
            read_timeout=execution_timeout_seconds,
        )
        try:
            stdout, stderr, exit_code = self._invoke_powershell_script(client, script_text, parameters)
        except (AuthenticationError, SpnegoError) as exc:
            raise WinRMAuthError(str(exc)) from exc
        except (requests.exceptions.ConnectTimeout, requests.exceptions.ReadTimeout, TimeoutError) as exc:
            raise TimeoutError(str(exc)) from exc
        except requests.exceptions.ConnectionError as exc:
            raise WinRMUnreachableError(str(exc)) from exc
        except WinRMTransportError as exc:
            message = str(exc).lower()
            if any(k in message for k in ("401", "auth", "credential", "logon", "logowania", "denied", "forbidden", "access", "dostępu")):
                raise WinRMAuthError(str(exc)) from exc
            if "timed out" in message or "timeout" in message:
                raise TimeoutError(str(exc)) from exc
            if "refused" in message or "unreachable" in message or "failed to connect" in message:
                raise WinRMUnreachableError(str(exc)) from exc
            raise DomainTransportError(str(exc)) from exc
        except WinRMError as exc:
            raise DomainTransportError(str(exc)) from exc
        except OSError as exc:
            raise WinRMUnreachableError(str(exc)) from exc

        return TransportResult(exit_code=exit_code, stdout=stdout, stderr=stderr)

    def _invoke_powershell_script(
        self,
        client: Client,
        script_text: str,
        parameters: dict[str, Any],
    ) -> tuple[str, str, int]:
        with RunspacePool(client.wsman, no_profile=True) as pool:
            powershell = PowerShell(pool)
            powershell.add_script("$ErrorActionPreference = 'Stop'").add_statement()
            powershell.add_script("$ProgressPreference = 'SilentlyContinue'").add_statement()
            powershell.add_script(script_text).add_parameters({"InputParameters": parameters})
            output = powershell.invoke()

        stdout = "\n".join("" if item is None else str(item) for item in output).strip()
        stderr = self._format_streams(powershell.streams)
        exit_code = self._extract_exit_code(stdout, stderr, powershell.had_errors)
        return stdout, stderr, exit_code

    def _format_streams(self, streams: Any) -> str:
        lines: list[str] = []
        for stream_name in ("error", "warning", "verbose", "debug", "information"):
            for record in getattr(streams, stream_name, []):
                text = str(record).strip()
                if text:
                    lines.append(text)
        return "\n".join(lines)

    def _extract_exit_code(self, stdout: str, stderr: str, had_errors: bool) -> int:
        if had_errors:
            return 1
        if stderr:
            return 1
        return 0

    def _to_powershell_literal(self, value: Any) -> str:
        if isinstance(value, dict):
            items = [f"{key} = {self._to_powershell_literal(item)}" for key, item in value.items()]
            return "@{" + "; ".join(items) + "}"
        if isinstance(value, list):
            return "@(" + ", ".join(self._to_powershell_literal(item) for item in value) + ")"
        if isinstance(value, bool):
            return "$true" if value else "$false"
        if value is None:
            return "$null"
        if isinstance(value, (int, float)):
            return str(value)
        escaped = str(value).replace("'", "''")
        return f"'{escaped}'"


class WinRMClient:
    def __init__(self, transport: Transport | None = None) -> None:
        self.transport = transport or PypsrpTransport()

    async def execute(
        self,
        hostname: str,
        script_path: Path,
        parameters: dict[str, Any],
        connect_timeout_seconds: int,
        execution_timeout_seconds: int,
        auth: str,
        credentials: WinRMCredentials | None = None,
    ) -> TransportResult:
        return await self.transport.run_script(
            hostname=hostname,
            script_path=script_path,
            parameters=parameters,
            connect_timeout_seconds=connect_timeout_seconds,
            execution_timeout_seconds=execution_timeout_seconds,
            auth=auth,
            credentials=credentials,
        )
