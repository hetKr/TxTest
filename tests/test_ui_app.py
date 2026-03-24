import asyncio
from pathlib import Path

from textual.widgets import Button, Input, Log

from txtest.services.credentials import CredentialPromptCancelledError, WinRMCredentials
from txtest.ui.app import TxTestApp


def test_dry_run_uses_valid_defaults(mock_orchestrator) -> None:
    app = TxTestApp(
        Path(__file__).resolve().parents[1],
        orchestrator=mock_orchestrator,
        operator_provider=lambda: "stako.local\\krystian.hettman",
    )

    async def scenario() -> None:
        async with app.run_test():
            assert app.query_one("#station-id", Input).value == "ST01"
            assert app.query_one("#package-name", Input).value == "basic_healthcheck"
            assert app.query_one("#operator", Input).value == "stako.local\\krystian.hettman"

            await app.on_button_pressed(Button.Pressed(app.query_one("#dry-run", Button)))

            log = app.query_one("#run-log", Log)
            assert log.lines
            assert log.lines[-1].startswith("Dry run plan: [")
    asyncio.run(scenario())


def test_start_logs_error_instead_of_crashing_for_unknown_station(mock_orchestrator) -> None:
    app = TxTestApp(Path(__file__).resolve().parents[1], orchestrator=mock_orchestrator)

    async def scenario() -> None:
        async with app.run_test():
            app.query_one("#station-id", Input).value = "BOGUS"

            await app.on_button_pressed(Button.Pressed(app.query_one("#start", Button)))

            log = app.query_one("#run-log", Log)
            assert log.lines[-1] == "KeyError: 'Unknown station_id: BOGUS'"
    asyncio.run(scenario())


def test_app_prompts_for_credentials_on_startup_and_reuses_them_for_start(mock_orchestrator) -> None:
    captured = {"calls": 0}

    def credential_provider(target_name: str) -> WinRMCredentials:
        captured["calls"] += 1
        captured["target_name"] = target_name
        return WinRMCredentials(username="DOMAIN\\operator1", password="secret")

    app = TxTestApp(
        Path(__file__).resolve().parents[1],
        orchestrator=mock_orchestrator,
        credential_provider=credential_provider,
        operator_provider=lambda: "stako.local\\krystian.hettman",
    )
    app._requires_interactive_credentials = lambda: True

    async def scenario() -> None:
        async with app.run_test():
            assert app.query_one("#operator", Input).value == "DOMAIN\\operator1"
            assert "Authenticated as DOMAIN\\operator1" in app.query_one("#dashboard-status").renderable
            await app.on_button_pressed(Button.Pressed(app.query_one("#start", Button)))

            log = app.query_one("#run-log", Log)
            assert any("Windows login completed for ST01 (startup)" in line for line in log.lines)
            assert any("Using cached Windows credentials for ST01" in line for line in log.lines)
            assert captured["target_name"] == "PLSLU-BP8D1G3.stako.local"
            assert captured["calls"] == 1
            assert not mock_orchestrator._run_credentials

    asyncio.run(scenario())


def test_start_reprompts_if_startup_login_was_cancelled(mock_orchestrator) -> None:
    captured = {"calls": 0}

    def credential_provider(target_name: str) -> WinRMCredentials:
        captured["calls"] += 1
        if captured["calls"] == 1:
            raise CredentialPromptCancelledError("cancelled")
        return WinRMCredentials(username="DOMAIN\\operator1", password="secret")

    app = TxTestApp(
        Path(__file__).resolve().parents[1],
        orchestrator=mock_orchestrator,
        credential_provider=credential_provider,
        operator_provider=lambda: "stako.local\\krystian.hettman",
    )
    app._requires_interactive_credentials = lambda: True

    async def scenario() -> None:
        async with app.run_test():
            assert app.query_one("#operator", Input).value == "stako.local\\krystian.hettman"
            dashboard_status = str(app.query_one("#dashboard-status").renderable)
            assert "Not authenticated" in dashboard_status
            assert "Startup Windows login was cancelled" in dashboard_status

            await app.on_button_pressed(Button.Pressed(app.query_one("#start", Button)))

            log = app.query_one("#run-log", Log)
            assert any("Startup Windows login cancelled" in line for line in log.lines)
            assert any("Windows login completed for ST01 (deferred start)" in line for line in log.lines)
            assert any("Using cached Windows credentials for ST01" in line for line in log.lines)
            assert app.query_one("#operator", Input).value == "DOMAIN\\operator1"
            assert captured["calls"] == 2

    asyncio.run(scenario())


def test_start_stays_blocked_when_login_is_cancelled_again(mock_orchestrator) -> None:
    def credential_provider(target_name: str) -> WinRMCredentials:
        raise CredentialPromptCancelledError("cancelled")

    app = TxTestApp(
        Path(__file__).resolve().parents[1],
        orchestrator=mock_orchestrator,
        credential_provider=credential_provider,
        operator_provider=lambda: "stako.local\\krystian.hettman",
    )
    app._requires_interactive_credentials = lambda: True

    async def scenario() -> None:
        async with app.run_test():
            await app.on_button_pressed(Button.Pressed(app.query_one("#start", Button)))

            log = app.query_one("#run-log", Log)
            assert log.lines[-1] == "Credential prompt cancelled"
            assert not mock_orchestrator.queue
            assert "Windows login is still required" in str(app.query_one("#dashboard-status").renderable)

    asyncio.run(scenario())


def test_operator_field_prefills_without_winrm_login(mock_orchestrator) -> None:
    def credential_provider(target_name: str) -> WinRMCredentials:
        raise CredentialPromptCancelledError("cancelled")

    app = TxTestApp(
        Path(__file__).resolve().parents[1],
        orchestrator=mock_orchestrator,
        credential_provider=credential_provider,
        operator_provider=lambda: "STAKO\\krystian.hettman",
    )
    app._requires_interactive_credentials = lambda: True

    async def scenario() -> None:
        async with app.run_test():
            assert app.query_one("#operator", Input).value == "STAKO\\krystian.hettman"
            assert "Not authenticated" in str(app.query_one("#dashboard-status").renderable)

    asyncio.run(scenario())
