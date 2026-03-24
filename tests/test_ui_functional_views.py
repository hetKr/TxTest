import asyncio
import json

from textual.widgets import Button, Log, OptionList, Static, TextArea

from txtest.models.core import TransportResult
from txtest.ui.app import TxTestApp
from txtest.services.winrm import MockTransport, WinRMClient


def test_scripts_tab_renders_manifest_and_script_contents(test_repo_root, mock_orchestrator) -> None:
    app = TxTestApp(test_repo_root, orchestrator=mock_orchestrator)

    async def scenario() -> None:
        async with app.run_test():
            scripts_list = app.query_one("#scripts-list", OptionList)
            scripts_detail = app.query_one("#scripts-detail", TextArea)
            assert scripts_list.option_count > 0
            assert "disk_free_space.manifest.yaml" in scripts_detail.text
            assert "script_file: disk_free_space.ps1" in scripts_detail.text
            assert "disk_free_space.ps1" in scripts_detail.text
    asyncio.run(scenario())


def test_start_generates_report_and_audit_artifacts_and_updates_views(test_repo_root, mock_orchestrator) -> None:
    app = TxTestApp(test_repo_root, orchestrator=mock_orchestrator)

    reports_dir = test_repo_root / "reports"
    audit_dir = test_repo_root / "audit"
    before_reports = set(reports_dir.glob("*.json"))
    before_audit = set(audit_dir.glob("*.json"))

    async def scenario() -> None:
        async with app.run_test():
            await app.on_button_pressed(Button.Pressed(app.query_one("#start", Button)))

            log = app.query_one("#run-log", Log)
            assert any(line.startswith("Finished ") for line in log.lines)

            history_detail = app.query_one("#history-detail", TextArea)
            audit_detail = app.query_one("#audit-detail", TextArea)
            status_view = app.query_one("#dashboard-status", Static)

            assert "winrm-remote" in history_detail.text
            assert "run_finished" in audit_detail.text
            assert "Queued: 0" in str(status_view.renderable)
            assert "Active: 0" in str(status_view.renderable)
    asyncio.run(scenario())

    after_reports = set(reports_dir.glob("*.json"))
    after_audit = set(audit_dir.glob("*.json"))

    new_reports = sorted(after_reports - before_reports)
    new_audit = sorted(after_audit - before_audit)
    assert new_reports, "expected at least one new report JSON file"
    assert new_audit, "expected at least one new audit JSON file"

    report_payload = json.loads(new_reports[-1].read_text(encoding="utf-8"))
    assert report_payload["environment_snapshot"]["mode"] == "winrm-remote"
    assert report_payload["results"], "expected result rows in report"


def test_history_and_audit_views_show_existing_json_files(test_repo_root, mock_orchestrator) -> None:
    run_id = "ui-functional-history-test"
    report_path = test_repo_root / "reports" / f"{run_id}.json"
    audit_path = test_repo_root / "audit" / f"{run_id}.json"
    report_path.write_text(json.dumps({"run_id": run_id, "hello": "history"}, indent=2), encoding="utf-8")
    audit_path.write_text(json.dumps({"run_id": run_id, "action": "history-test"}, indent=2), encoding="utf-8")

    app = TxTestApp(test_repo_root, orchestrator=mock_orchestrator)
    async def scenario() -> None:
        async with app.run_test():
            history_detail = app.query_one("#history-detail", TextArea)
            audit_detail = app.query_one("#audit-detail", TextArea)
            assert run_id in history_detail.text
            assert "history" in history_detail.text
            assert run_id in audit_detail.text
            assert "history-test" in audit_detail.text
    asyncio.run(scenario())


def test_history_view_shows_persisted_invalid_output_diagnostics(test_repo_root, mock_orchestrator) -> None:
    station = mock_orchestrator.stations_config.stations[0]
    mock_orchestrator.winrm_client = WinRMClient(
        transport=MockTransport(
            {
                f"{station.host}:preflight_check.ps1": TransportResult(
                    stdout="not-json-from-psrp",
                    stderr="stderr-from-psrp",
                    exit_code=9,
                )
            }
        )
    )
    app = TxTestApp(test_repo_root, orchestrator=mock_orchestrator)

    async def scenario() -> None:
        async with app.run_test():
            await app.on_button_pressed(Button.Pressed(app.query_one("#start", Button)))
            history_detail = app.query_one("#history-detail", TextArea)
            assert "transport_diagnostics" in history_detail.text
            assert "raw_stdout" in history_detail.text
            assert "not-json-from-psrp" in history_detail.text
            assert "stderr-from-psrp" in history_detail.text
            assert '"exit_code": 9' in history_detail.text

    asyncio.run(scenario())
