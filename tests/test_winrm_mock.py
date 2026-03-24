from pathlib import Path

import pytest

from txtest.models.core import TransportResult
from txtest.services.error_mapper import WinRMTransportError
from txtest.services.winrm import MockTransport, PypsrpTransport, WinRMClient


@pytest.mark.asyncio
async def test_mock_transport_response() -> None:
    client = WinRMClient(
        transport=MockTransport(
            {
                "PLSLU-BP8D1G3.stako.local:preflight_check.ps1": TransportResult(stdout="{}", stderr="", exit_code=0)
            }
        )
    )
    result = await client.execute(
        "PLSLU-BP8D1G3.stako.local",
        Path("scripts/preflight_check.ps1"),
        {},
        connect_timeout_seconds=5,
        execution_timeout_seconds=30,
        auth="kerberos",
    )
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_mock_transport_missing_response() -> None:
    client = WinRMClient(transport=MockTransport())
    with pytest.raises(WinRMTransportError):
        await client.execute(
            "host",
            Path("missing.ps1"),
            {},
            connect_timeout_seconds=5,
            execution_timeout_seconds=30,
            auth="kerberos",
        )


def test_pypsrp_transport_invokes_script_with_named_parameters(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {"scripts": []}

    class FakeRunspacePool:
        def __init__(self, wsman, no_profile=False):
            captured["wsman"] = wsman
            captured["no_profile"] = no_profile

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return None

    class FakeStreams:
        error = []
        warning = []
        verbose = []
        debug = []
        information = []

    class FakePowerShell:
        def __init__(self, pool):
            captured["pool"] = pool
            self.streams = FakeStreams()
            self.had_errors = False

        def add_script(self, script):
            captured["scripts"].append(script)
            return self

        def add_statement(self):
            return self

        def add_parameters(self, parameters):
            captured["parameters"] = parameters
            return self

        def invoke(self):
            return ['{"status":"PASS"}']

    monkeypatch.setattr("txtest.services.winrm.RunspacePool", FakeRunspacePool)
    monkeypatch.setattr("txtest.services.winrm.PowerShell", FakePowerShell)

    transport = PypsrpTransport()
    client = type("FakeClient", (), {"wsman": object()})()

    stdout, stderr, exit_code = transport._invoke_powershell_script(
        client,
        "param([hashtable]$InputParameters)\n$InputParameters | ConvertTo-Json -Compress",
        {"name": "value"},
    )

    assert captured["no_profile"] is True
    assert captured["parameters"] == {"InputParameters": {"name": "value"}}
    assert "$ErrorActionPreference = 'Stop'" in captured["scripts"]
    assert "$ProgressPreference = 'SilentlyContinue'" in captured["scripts"]
    assert any("param([hashtable]$InputParameters)" in s for s in captured["scripts"])
    assert stdout == '{"status":"PASS"}'
    assert stderr == ""
    assert exit_code == 0
