from datetime import datetime, timezone
from txtest.models.domain import AttemptSummary, DomainStatus, HostInfo, PackageRunReport, RunSummary, ScriptResult, Severity, TerminationReason
from txtest.services.reporting import ReportService


def build_report() -> PackageRunReport:
    return PackageRunReport(
        run_id="run-1",
        correlation_id="corr-1",
        station_id="ST01",
        station_name="Station 01",
        package_name="basic_healthcheck",
        operator="DOMAIN\\operator1",
        config_version="1.0.0",
        started_at_utc=datetime.now(timezone.utc),
        finished_at_utc=datetime.now(timezone.utc),
        duration_ms=100,
        final_status=DomainStatus.PASS,
        termination_reason=TerminationReason.COMPLETED,
        results=[ScriptResult(test_name="disk_free_space", status=DomainStatus.PASS, message="ok", value="1", timestamp_utc=datetime.now(timezone.utc), duration_ms=1, error_code=None, severity=Severity.INFO, details={}, host_info=HostInfo(hostname="ST01", ip="1.1.1.1"), script_version="1.0.0", attempt_no=1, artifacts=[])],
        summary=RunSummary(passed=1),
        attempt_summary=AttemptSummary(total_attempts=1),
    )


def test_report_exports(workspace_temp_dir) -> None:
    service = ReportService(workspace_temp_dir)
    report = build_report()
    assert service.write_json(report).exists()
    assert service.write_csv(report).exists()
    assert service.write_html(report).exists()
