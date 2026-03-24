import json
import asyncio
from pathlib import Path

from txtest.models.core import TransportResult
from txtest.models.domain import PackageDefinition, Severity, StationDefinition
from txtest.services.error_mapper import WinRMAuthError
from txtest.services.orchestrator import Orchestrator
from txtest.services.state_store import QueueStateStore
from txtest.services.winrm import MockTransport, WinRMClient


station = StationDefinition(station_id="ST01", station_name="Station 01", host="PLSLU-BP8D1G3.stako.local", ip="10.122.7.119", auth="kerberos", tags=[])
package = PackageDefinition(package_name="basic_healthcheck", description="d", tests=[])


def test_enqueue_and_cancel(workspace_temp_dir) -> None:
    orchestrator = Orchestrator(QueueStateStore(workspace_temp_dir))
    run = orchestrator.enqueue(station, package, "operator")
    assert run.station_id == "ST01"
    orchestrator.request_cancel(run.run_id)
    assert orchestrator.queue[0].cancellation_requested is True


def test_process_queue_runs_real_pipeline_with_mocked_transport(mock_orchestrator) -> None:
    run = mock_orchestrator.request_run("ST01", "basic_healthcheck", "operator")

    asyncio.run(mock_orchestrator.process_queue())

    report_path = mock_orchestrator.report_service.reports_dir / f"{run.run_id}.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["environment_snapshot"]["mode"] == "winrm-remote"
    assert payload["environment_snapshot"]["transport"] == "MockTransport"
    assert payload["results"]
    assert payload["final_status"] == "PASS"


def test_process_queue_maps_auth_failures_to_domain_status(mock_orchestrator) -> None:
    class FailingTransport:
        async def run_script(
            self,
            hostname: str,
            script_path: Path,
            parameters: dict,
            connect_timeout_seconds: int,
            execution_timeout_seconds: int,
            auth: str,
            credentials=None,
        ):
            raise WinRMAuthError("bad credentials")

    mock_orchestrator.winrm_client = WinRMClient(transport=FailingTransport())
    run = mock_orchestrator.request_run("ST01", "basic_healthcheck", "operator")

    asyncio.run(mock_orchestrator.process_queue())

    report_path = mock_orchestrator.report_service.reports_dir / f"{run.run_id}.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["final_status"] == "AUTH_FAILED"
    assert payload["termination_reason"] == "FAIL_FAST"
    assert payload["results"][0]["status"] == "AUTH_FAILED"


def test_process_queue_persists_transport_diagnostics_for_invalid_json(mock_orchestrator) -> None:
    station = mock_orchestrator.stations_config.stations[0]
    large_stdout = ("stdout-prefix-" + ("A" * 5000) + "-stdout-suffix")
    large_stderr = ("stderr-prefix-" + ("B" * 5000) + "-stderr-suffix")
    mock_orchestrator.winrm_client = WinRMClient(
        transport=MockTransport(
            {
                f"{station.host}:preflight_check.ps1": TransportResult(
                    stdout=large_stdout,
                    stderr=large_stderr,
                    exit_code=17,
                )
            }
        )
    )
    run = mock_orchestrator.request_run("ST01", "basic_healthcheck", "operator")

    asyncio.run(mock_orchestrator.process_queue())

    report_path = mock_orchestrator.report_service.reports_dir / f"{run.run_id}.json"
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    result = payload["results"][0]
    diagnostics = result["details"]["transport_diagnostics"]

    assert payload["final_status"] == "INVALID_OUTPUT"
    assert result["status"] == "INVALID_OUTPUT"
    assert diagnostics["exit_code"] == 17
    assert diagnostics["raw_stdout_truncated"] is True
    assert diagnostics["raw_stderr_truncated"] is True
    assert diagnostics["raw_stdout_original_length"] == len(large_stdout)
    assert diagnostics["raw_stderr_original_length"] == len(large_stderr)
    assert diagnostics["raw_stdout"].startswith("stdout-prefix-")
    assert diagnostics["raw_stdout"].endswith("-stdout-suffix")
    assert diagnostics["raw_stderr"].startswith("stderr-prefix-")
    assert diagnostics["raw_stderr"].endswith("-stderr-suffix")
    assert len(diagnostics["raw_stdout"]) <= mock_orchestrator.MAX_DIAGNOSTIC_TEXT_CHARS
    assert len(diagnostics["raw_stderr"]) <= mock_orchestrator.MAX_DIAGNOSTIC_TEXT_CHARS

    html_path = mock_orchestrator.report_service.reports_dir / f"{run.run_id}.html"
    html = html_path.read_text(encoding="utf-8")
    assert "transport_diagnostics" in html
    assert "raw_stdout" in html
