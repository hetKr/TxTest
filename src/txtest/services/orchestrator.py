from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from txtest.models.domain import (
    AttemptSummary,
    AuditEntry,
    DomainStatus,
    HostInfo,
    PackageDefinition,
    PackageRunReport,
    PackagesConfig,
    QueueRun,
    RunState,
    RunSummary,
    ScriptManifest,
    ScriptResult,
    Severity,
    StationDefinition,
    StationsConfig,
    TerminationReason,
)
from txtest.services.audit import AuditService
from txtest.services.config_loader import ConfigLoader
from txtest.services.credentials import WinRMCredentials
from txtest.services.error_mapper import ErrorMapper
from txtest.services.reporting import ReportService
from txtest.services.result_parser import InvalidJsonResultError, ResultParser
from txtest.services.state_store import QueueStateStore
from txtest.services.winrm import WinRMClient


class Orchestrator:
    MAX_DIAGNOSTIC_TEXT_CHARS = 4000

    def __init__(
        self,
        state_store: QueueStateStore,
        stations_config: StationsConfig | None = None,
        packages_config: PackagesConfig | None = None,
        report_service: ReportService | None = None,
        audit_service: AuditService | None = None,
        winrm_client: WinRMClient | None = None,
        config_loader: ConfigLoader | None = None,
        result_parser: ResultParser | None = None,
        error_mapper: ErrorMapper | None = None,
        scripts_dir: Path | None = None,
    ) -> None:
        self.state_store = state_store
        self.stations_config = stations_config
        self.packages_config = packages_config
        self.report_service = report_service
        self.audit_service = audit_service
        self.winrm_client = winrm_client or WinRMClient()
        self.config_loader = config_loader or ConfigLoader()
        self.result_parser = result_parser or ResultParser()
        self.error_mapper = error_mapper or ErrorMapper()
        self.scripts_dir = scripts_dir or Path("scripts")
        self.queue: list[QueueRun] = []
        self.active: list[QueueRun] = []
        self._run_credentials: dict[str, WinRMCredentials] = {}

    def enqueue(
        self,
        station: StationDefinition,
        package: PackageDefinition,
        operator: str,
        credentials: WinRMCredentials | None = None,
    ) -> QueueRun:
        timestamp = datetime.now(timezone.utc)
        run = QueueRun(
            run_id=(
                f"{timestamp:%Y%m%d_%H%M%S_%f}_{station.station_id}_{package.package_name}"
            ),
            correlation_id=str(uuid4()),
            station_id=station.station_id,
            package_name=package.package_name,
            operator=operator,
        )
        self.queue.append(run)
        if credentials is not None:
            self._run_credentials[run.run_id] = credentials
        self.state_store.save(self.queue + self.active)
        self._record_audit(
            operator=operator,
            action="run_queued",
            target_type="run",
            target_id=run.run_id,
            run_id=run.run_id,
            details={"station_id": station.station_id, "package_name": package.package_name},
        )
        return run

    def request_run(
        self,
        station_id: str,
        package_name: str,
        operator: str,
        credentials: WinRMCredentials | None = None,
    ) -> QueueRun:
        station = self._get_station(station_id)
        package = self._get_package(package_name)
        return self.enqueue(station, package, operator, credentials=credentials)

    def request_cancel(self, run_id: str) -> bool:
        for item in [*self.active, *self.queue]:
            if item.run_id == run_id:
                item.cancellation_requested = True
                item.state = RunState.CANCELLATION_REQUESTED
                self.state_store.save(self.queue + self.active)
                self._record_audit(
                    operator=item.operator,
                    action="run_cancellation_requested",
                    target_type="run",
                    target_id=run_id,
                    run_id=run_id,
                    details={"state": item.state.value},
                )
                return True
        return False

    def cancel_run(self, run_id: str, operator: str | None = None) -> bool:
        return self.request_cancel(run_id)

    async def process_queue(self) -> None:
        while self.queue:
            run = self.queue.pop(0)
            run.state = RunState.RUNNING
            self.active.append(run)
            self.state_store.save(self.queue + self.active)
            self._record_audit(
                operator=run.operator,
                action="run_started",
                target_type="run",
                target_id=run.run_id,
                run_id=run.run_id,
                details={"station_id": run.station_id, "package_name": run.package_name},
            )

            report = await self._execute_run(run)
            run.final_status = report.final_status
            run.termination_reason = report.termination_reason
            run.state = RunState.FINISHED

            if self.report_service is not None:
                self.report_service.write_json(report)
                self.report_service.write_html(report)
                self.report_service.write_csv(report)

            self._record_audit(
                operator=run.operator,
                action="run_finished",
                target_type="run",
                target_id=run.run_id,
                run_id=run.run_id,
                details={
                    "final_status": run.final_status.value if run.final_status else None,
                    "termination_reason": run.termination_reason.value if run.termination_reason else None,
                    "results": len(report.results),
                    "target_host": report.environment_snapshot.get("target_host"),
                    "transport": report.environment_snapshot.get("transport"),
                },
            )

            self.active = [item for item in self.active if item.run_id != run.run_id]
            self.state_store.save(self.queue + self.active)

    async def dry_run(self, station_id: str, package_name: str) -> dict:
        station = self._get_station(station_id)
        package = self._get_package(package_name)
        plan: list[dict[str, str | int]] = []
        for test in package.tests:
            manifest = self._load_manifest(test.manifest)
            plan.append(
                {
                    "test_name": test.name,
                    "manifest": test.manifest,
                    "script_file": manifest.script_file,
                    "timeout_seconds": test.timeout_seconds,
                    "retry_count": test.retry_count,
                }
            )
        return {
            "station_id": station.station_id,
            "station_host": station.host,
            "package_name": package.package_name,
            "plan": plan,
        }

    async def _execute_run(self, run: QueueRun) -> PackageRunReport:
        station = self._get_station(run.station_id)
        package = self._get_package(run.package_name)
        credentials = self._run_credentials.get(run.run_id)
        started_at = datetime.now(timezone.utc)
        results: list[ScriptResult] = []
        event_log: list[dict[str, object]] = [
            {"event": "run_started", "timestamp_utc": started_at.isoformat(), "host": station.host}
        ]
        total_attempts = 0
        retried_tests = 0
        final_status = DomainStatus.PASS
        termination_reason = TerminationReason.COMPLETED

        for test in package.tests:
            if run.cancellation_requested:
                final_status = DomainStatus.ABORTED
                termination_reason = TerminationReason.OPERATOR_CANCEL
                break

            manifest = self._load_manifest(test.manifest)
            event_log.append(
                {
                    "event": "test_started",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "test_name": test.name,
                    "manifest": test.manifest,
                    "script_file": manifest.script_file,
                }
            )
            result = await self._execute_test(
                station,
                test.name,
                test.parameters,
                test.timeout_seconds,
                test.retry_count,
                test.retry_backoff_seconds,
                test.severity,
                manifest,
                credentials,
            )
            total_attempts += result.attempt_no
            if result.attempt_no > 1:
                retried_tests += 1
            results.append(result)
            event_log.append(
                {
                    "event": "test_finished",
                    "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                    "test_name": test.name,
                    "status": result.status.value,
                    "attempt_no": result.attempt_no,
                }
            )

            if result.status not in {DomainStatus.PASS, DomainStatus.SKIPPED}:
                final_status = self._promote_final_status(final_status, result.status)
                if not test.continue_on_fail:
                    termination_reason = TerminationReason.FAIL_FAST
                    break

        if final_status == DomainStatus.PASS and run.cancellation_requested:
            final_status = DomainStatus.ABORTED
            termination_reason = TerminationReason.OPERATOR_CANCEL

        finished_at = datetime.now(timezone.utc)
        event_log.append(
            {
                "event": "run_finished",
                "timestamp_utc": finished_at.isoformat(),
                "final_status": final_status.value,
                "termination_reason": termination_reason.value,
            }
        )

        self._run_credentials.pop(run.run_id, None)
        return PackageRunReport(
            run_id=run.run_id,
            correlation_id=run.correlation_id,
            station_id=station.station_id,
            station_name=station.station_name,
            package_name=package.package_name,
            operator=run.operator,
            config_version=self.packages_config.schema_version if self.packages_config else "1.0.0",
            started_at_utc=started_at,
            finished_at_utc=finished_at,
            duration_ms=max(int((finished_at - started_at).total_seconds() * 1000), 0),
            final_status=final_status,
            termination_reason=termination_reason,
            environment_snapshot={
                "mode": "winrm-remote",
                "transport": type(self.winrm_client.transport).__name__,
                "target_host": station.host,
                "target_ip": station.ip,
                "auth": station.auth,
                "scripts_dir": str(self.scripts_dir),
            },
            results=results,
            summary=self._build_summary(results),
            event_log=event_log,
            attempt_summary=AttemptSummary(total_attempts=total_attempts, retried_tests=retried_tests),
        )

    async def _execute_test(
        self,
        station: StationDefinition,
        test_name: str,
        parameters: dict,
        timeout_seconds: int,
        retry_count: int,
        retry_backoff_seconds: int,
        severity: Severity,
        manifest: ScriptManifest,
        credentials: WinRMCredentials | None,
    ) -> ScriptResult:
        script_path = self.scripts_dir / manifest.script_file
        last_exception: Exception | None = None

        for attempt_no in range(1, retry_count + 2):
            try:
                transport_result = await self.winrm_client.execute(
                    hostname=station.host,
                    script_path=script_path,
                    parameters=parameters,
                    connect_timeout_seconds=min(timeout_seconds, 15),
                    execution_timeout_seconds=timeout_seconds,
                    auth=station.auth,
                    credentials=credentials,
                )
                try:
                    parsed = self.result_parser.parse_stdout(transport_result.stdout)
                except InvalidJsonResultError as exc:
                    raise InvalidJsonResultError(
                        str(exc),
                        stdout=transport_result.stdout,
                        stderr=transport_result.stderr,
                        exit_code=transport_result.exit_code,
                    ) from exc
                details = dict(parsed.details)
                details.update(
                    {
                        "manifest": manifest.name,
                        "script_file": manifest.script_file,
                        "exit_code": transport_result.exit_code,
                    }
                )
                if transport_result.stderr:
                    details["stderr"] = transport_result.stderr
                return parsed.model_copy(
                    update={
                        "test_name": test_name,
                        "severity": severity,
                        "attempt_no": attempt_no,
                        "details": details,
                    }
                )
            except Exception as exc:
                last_exception = exc
                if attempt_no <= retry_count and self.error_mapper.is_transient(exc):
                    if retry_backoff_seconds > 0:
                        await asyncio.sleep(retry_backoff_seconds)
                    continue
                break

        assert last_exception is not None
        return self._build_error_result(
            station=station,
            test_name=test_name,
            severity=severity,
            manifest=manifest,
            attempt_no=retry_count + 1,
            exc=last_exception,
        )

    def _build_error_result(
        self,
        *,
        station: StationDefinition,
        test_name: str,
        severity: Severity,
        manifest: ScriptManifest,
        attempt_no: int,
        exc: Exception,
    ) -> ScriptResult:
        status = self.error_mapper.map_exception(exc)
        message = str(exc) or type(exc).__name__
        if isinstance(exc, InvalidJsonResultError):
            message = f"Invalid script output: {message}"
        details = {
            "manifest": manifest.name,
            "script_file": manifest.script_file,
            "exception_type": type(exc).__name__,
        }
        transport_diagnostics = self._build_transport_diagnostics(exc)
        if transport_diagnostics is not None:
            details["transport_diagnostics"] = transport_diagnostics
        return ScriptResult(
            test_name=test_name,
            status=status,
            message=message,
            value=None,
            timestamp_utc=datetime.now(timezone.utc),
            duration_ms=0,
            error_code=type(exc).__name__,
            severity=severity,
            details=details,
            host_info=HostInfo(hostname=station.host, ip=station.ip),
            script_version=manifest.version,
            attempt_no=attempt_no,
            artifacts=[],
        )

    def _build_transport_diagnostics(self, exc: Exception) -> dict[str, object] | None:
        stdout = getattr(exc, "stdout", None)
        stderr = getattr(exc, "stderr", None)
        exit_code = getattr(exc, "exit_code", None)
        if stdout is None and stderr is None and exit_code is None:
            return None
        stdout_payload = self._truncate_diagnostic_text(stdout or "")
        stderr_payload = self._truncate_diagnostic_text(stderr or "")
        return {
            "exit_code": exit_code,
            "raw_stdout": stdout_payload["text"],
            "raw_stdout_truncated": stdout_payload["truncated"],
            "raw_stdout_original_length": stdout_payload["original_length"],
            "raw_stderr": stderr_payload["text"],
            "raw_stderr_truncated": stderr_payload["truncated"],
            "raw_stderr_original_length": stderr_payload["original_length"],
        }

    def _truncate_diagnostic_text(self, value: str) -> dict[str, object]:
        original_length = len(value)
        limit = self.MAX_DIAGNOSTIC_TEXT_CHARS
        if original_length <= limit:
            return {"text": value, "truncated": False, "original_length": original_length}
        marker = "\n...[truncated output]...\n"
        available = max(limit - len(marker), 0)
        prefix_length = available // 2
        suffix_length = available - prefix_length
        omitted_length = original_length - prefix_length - suffix_length
        marker = f"\n...[truncated {omitted_length} chars]...\n"
        available = max(limit - len(marker), 0)
        prefix_length = available // 2
        suffix_length = available - prefix_length
        suffix = value[-suffix_length:] if suffix_length else ""
        text = f"{value[:prefix_length]}{marker}{suffix}"
        return {"text": text, "truncated": True, "original_length": original_length}

    def _build_summary(self, results: list[ScriptResult]) -> RunSummary:
        summary = RunSummary()
        for result in results:
            if result.status is DomainStatus.PASS:
                summary.passed += 1
            elif result.status is DomainStatus.FAIL:
                summary.failed += 1
            elif result.status is DomainStatus.SKIPPED:
                summary.skipped += 1
            elif result.status is DomainStatus.TIMEOUT:
                summary.timeouts += 1
            else:
                summary.errors += 1
        return summary

    def _promote_final_status(self, current: DomainStatus, candidate: DomainStatus) -> DomainStatus:
        precedence = {
            DomainStatus.PASS: 0,
            DomainStatus.SKIPPED: 1,
            DomainStatus.FAIL: 2,
            DomainStatus.INVALID_OUTPUT: 3,
            DomainStatus.ERROR: 4,
            DomainStatus.TIMEOUT: 5,
            DomainStatus.UNREACHABLE: 6,
            DomainStatus.AUTH_FAILED: 7,
            DomainStatus.ABORTED: 8,
        }
        return candidate if precedence[candidate] >= precedence[current] else current

    def _load_manifest(self, manifest_name: str) -> ScriptManifest:
        return self.config_loader.load_manifest(self.scripts_dir / manifest_name)

    def _get_station(self, station_id: str) -> StationDefinition:
        if self.stations_config is None:
            raise ValueError("Stations configuration is not loaded")
        for station in self.stations_config.stations:
            if station.station_id == station_id:
                return station
        raise KeyError(f"Unknown station_id: {station_id}")

    def _get_package(self, package_name: str) -> PackageDefinition:
        if self.packages_config is None:
            raise ValueError("Packages configuration is not loaded")
        for package in self.packages_config.packages:
            if package.package_name == package_name:
                return package
        raise KeyError(f"Unknown package_name: {package_name}")

    def _record_audit(
        self,
        *,
        operator: str,
        action: str,
        target_type: str,
        target_id: str,
        run_id: str | None,
        details: dict,
    ) -> None:
        if self.audit_service is None:
            return
        self.audit_service.record(
            AuditEntry(
                operator=operator,
                action=action,
                target_type=target_type,
                target_id=target_id,
                run_id=run_id,
                details=details,
            )
        )
