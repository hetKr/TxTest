from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable

from textual.app import App, ComposeResult
from textual.css.query import NoMatches
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Label, Log, OptionList, Static, TabbedContent, TabPane, TextArea
from txtest.app_context import build_orchestrator
from txtest.services.credentials import (
    CredentialPromptCancelledError,
    WinRMCredentials,
    WindowsCredentialPrompt,
    WindowsCredentialPromptUnavailableError,
    detect_current_operator,
)
from txtest.services.orchestrator import Orchestrator
from txtest.services.winrm import PypsrpTransport


class TxTestApp(App):
    CSS = """
    Screen { layout: vertical; }
    #dashboard { height: auto; padding: 1; }
    #dashboard-status { height: 1fr; padding: 1; border: solid gray; }
    #run-log { height: 16; border: solid green; }
    .browser { height: 1fr; }
    .browser OptionList { width: 35%; min-width: 24; border: solid gray; }
    .browser TextArea { width: 1fr; border: solid gray; }
    #operator {
        margin: 0 0 1 0
    }
    Button {
        height: 3;       
        margin: 0 1;     
         
    }
    
    """

    def __init__(
        self,
        repo_root: Path,
        orchestrator: Orchestrator | None = None,
        credential_provider: Callable[[str], WinRMCredentials] | None = None,
        operator_provider: Callable[[], str] | None = None,
    ) -> None:
        super().__init__()
        self.repo_root = repo_root
        self.orchestrator = orchestrator or build_orchestrator(repo_root)
        self.credential_provider = credential_provider or self._prompt_for_winrm_credentials
        self.operator_provider = operator_provider or detect_current_operator
        self._queue_task: asyncio.Task | None = None

        stations = self.orchestrator.stations_config.stations if self.orchestrator.stations_config else []
        packages = self.orchestrator.packages_config.packages if self.orchestrator.packages_config else []
        self.default_station_id = stations[0].station_id if stations else ""
        self.default_package_name = packages[0].package_name if packages else ""
        self.default_operator = self.operator_provider()
        self._session_credentials: WinRMCredentials | None = None
        self._auth_status = "Not authenticated"
        self._auth_detail = "Windows login was not completed for this session."

    def compose(self) -> ComposeResult:
        yield Header()
        with TabbedContent():
            with TabPane("Dashboard"):
                with Container(id="dashboard"):
                    yield Label("Station ID")
                    yield Input(value=self.default_station_id, id="station-id")
                    yield Label("Package")
                    yield Input(value=self.default_package_name, id="package-name")
                    yield Label("Operator")
                    yield Input(value=self.default_operator, id="operator")
                    with Horizontal():
                        yield Button("Start", id="start")
                        yield Button("Cancel Latest", id="cancel")
                        yield Button("Dry Run", id="dry-run")

                    yield Static("", id="dashboard-status")
                    yield Log(id="run-log")
            with TabPane("Stations"):
                yield Static(self._safe_read_text(self.repo_root / "configs/stations.yaml"))
            with TabPane("Packages"):
                yield Static(self._safe_read_text(self.repo_root / "configs/packages.yaml"))
            with TabPane("Scripts"):
                with Horizontal(classes="browser"):
                    yield OptionList(id="scripts-list")
                    yield TextArea("", id="scripts-detail", read_only=True, soft_wrap=False)
            with TabPane("History"):
                with Horizontal(classes="browser"):
                    yield OptionList(id="history-list")
                    yield TextArea("", id="history-detail", read_only=True, soft_wrap=False)
            with TabPane("Audit"):
                with Horizontal(classes="browser"):
                    yield OptionList(id="audit-list")
                    yield TextArea("", id="audit-detail", read_only=True, soft_wrap=False)
        yield Footer()

    async def on_mount(self) -> None:
        self._refresh_views()
        await self._authenticate_on_startup()

    def _safe_read_text(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return f"Missing file: {path}"

    def _list_scripts(self) -> list[tuple[str, str]]:
        scripts_dir = self.repo_root / "scripts"
        manifests = sorted(scripts_dir.glob("*.manifest.yaml"))
        items: list[tuple[str, str]] = []
        for manifest_path in manifests:
            manifest_text = self._safe_read_text(manifest_path)
            script_name = self._extract_script_name(manifest_text)
            items.append((manifest_path.name, script_name))
        return items

    def _render_script_detail(self, manifest_name: str) -> str:
        scripts_dir = self.repo_root / "scripts"
        manifest_path = scripts_dir / manifest_name
        manifest_text = self._safe_read_text(manifest_path)
        script_name = self._extract_script_name(manifest_text)
        script_path = scripts_dir / script_name if script_name else None
        script_text = self._safe_read_text(script_path) if script_path else "Script file not declared"
        return "\n".join(
            [
                f"=== {manifest_path.name} ===",
                manifest_text.strip(),
                "",
                f"--- {script_path.name if script_path else 'script'} ---",
                script_text.strip(),
            ]
        ).strip()

    def _extract_script_name(self, manifest_text: str) -> str:
        for line in manifest_text.splitlines():
            if line.strip().startswith("script_file:"):
                return line.split(":", 1)[1].strip().strip("\"'")
        return ""

    def _list_json_files(self, folder_name: str) -> list[Path]:
        folder = self.repo_root / folder_name
        return sorted(folder.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)

    def _render_json_detail(self, path: Path) -> str:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return json.dumps(payload, indent=2, ensure_ascii=False)
        except FileNotFoundError:
            return f"Missing file: {path}"
        except json.JSONDecodeError:
            return self._safe_read_text(path)

    def _ensure_queue_processor(self) -> None:
        if self._queue_task is None or self._queue_task.done():
            self._queue_task = asyncio.create_task(self.orchestrator.process_queue())

    async def _drain_queue(self) -> None:
        if self._queue_task is not None:
            await self._queue_task

    def _refresh_views(self) -> None:
        self.query_one("#dashboard-status", Static).update(self._render_dashboard_status())
        self._refresh_scripts_browser()
        self._refresh_json_browser("history", "reports")
        self._refresh_json_browser("audit", "audit")

    def _refresh_scripts_browser(self) -> None:
        if not self._has_widget("#scripts-list") or not self._has_widget("#scripts-detail"):
            return
        scripts = self._list_scripts()
        option_list = self.query_one("#scripts-list", OptionList)
        option_list.clear_options()
        if not scripts:
            option_list.add_option("No manifest files found")
            self.query_one("#scripts-detail", TextArea).load_text("No manifest files found in scripts/.")
            return
        option_list.add_options([f"{manifest} -> {script or '<missing script_file>'}" for manifest, script in scripts])
        option_list.highlighted = 0
        self.query_one("#scripts-detail", TextArea).load_text(self._render_script_detail(scripts[0][0]))

    def _refresh_json_browser(self, prefix: str, folder_name: str) -> None:
        if not self._has_widget(f"#{prefix}-list") or not self._has_widget(f"#{prefix}-detail"):
            return
        paths = self._list_json_files(folder_name)
        option_list = self.query_one(f"#{prefix}-list", OptionList)
        detail = self.query_one(f"#{prefix}-detail", TextArea)
        option_list.clear_options()
        if not paths:
            option_list.add_option(f"No JSON files in {folder_name}/")
            detail.load_text(f"No JSON files found in {folder_name}/.")
            return
        option_list.add_options([path.name for path in paths])
        option_list.highlighted = 0
        detail.load_text(self._render_json_detail(paths[0]))

    def _render_dashboard_status(self) -> str:
        queue_lines = [f"- {run.run_id} [{run.state}]" for run in self.orchestrator.queue]
        active_lines = [f"- {run.run_id} [{run.state}]" for run in self.orchestrator.active]
        queue_state_path = self.orchestrator.state_store.path
        return "\n".join(
            [
                f"Authentication: {self._auth_status}",
                f"Auth detail: {self._auth_detail}",
                "",
                f"Queued: {len(self.orchestrator.queue)}",
                f"Active: {len(self.orchestrator.active)}",
                f"State file: {queue_state_path}",
                "",
                "Queue:",
                *(queue_lines or ["- <empty>"]),
                "",
                "Active:",
                *(active_lines or ["- <empty>"]),
            ]
        )

    def _requires_interactive_credentials(self) -> bool:
        return isinstance(self.orchestrator.winrm_client.transport, PypsrpTransport)

    def _prompt_for_winrm_credentials(self, target_name: str) -> WinRMCredentials:
        prompt = WindowsCredentialPrompt()
        return prompt.prompt(
            target_name=target_name,
            message=f"Enter WinRM credentials for {target_name}",
        )

    def _set_authenticated_session(self, credentials: WinRMCredentials) -> None:
        self._session_credentials = credentials
        self._auth_status = f"Authenticated as {credentials.username}"
        self._auth_detail = "Windows credentials are cached in memory for this app session."
        if self._has_widget("#operator"):
            self.query_one("#operator", Input).value = credentials.username

    def _set_unauthenticated_session(self, detail: str) -> None:
        self._session_credentials = None
        self._auth_status = "Not authenticated"
        self._auth_detail = detail

    async def _prompt_for_session_credentials(self, station_id: str, *, reason: str) -> WinRMCredentials | None:
        station = self.orchestrator._get_station(station_id)
        credentials = await asyncio.to_thread(self.credential_provider, station.host)
        self._set_authenticated_session(credentials)
        self.query_one("#run-log", Log).write_line(f"Windows login completed for {station_id} ({reason})")
        self._refresh_views()
        return credentials

    async def _authenticate_on_startup(self) -> None:
        if not self._requires_interactive_credentials() or not self.default_station_id:
            if not self._requires_interactive_credentials():
                self._auth_status = "Using configured WinRM settings"
                self._auth_detail = "Interactive Windows login is not required by the active transport."
                self._refresh_views()
            return
        try:
            await self._prompt_for_session_credentials(self.default_station_id, reason="startup")
        except CredentialPromptCancelledError:
            self._set_unauthenticated_session("Startup Windows login was cancelled. Start will prompt again when needed.")
            self.query_one("#run-log", Log).write_line("Startup Windows login cancelled")
            self._refresh_views()
        except WindowsCredentialPromptUnavailableError:
            self._set_unauthenticated_session("Windows credential prompt is unavailable. Start will use configured WinRM settings.")
            self.query_one("#run-log", Log).write_line(
                "Windows credential prompt unavailable; falling back to configured WinRM environment settings"
            )
            self._refresh_views()

    async def _ensure_credentials_for_start(self, station_id: str) -> WinRMCredentials | None:
        if not self._requires_interactive_credentials():
            return None
        if self._session_credentials is not None:
            return self._session_credentials
        return await self._prompt_for_session_credentials(station_id, reason="deferred start")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        log = self.query_one("#run-log", Log)
        station_id = self.query_one("#station-id", Input).value.strip()
        package_name = self.query_one("#package-name", Input).value.strip()
        operator = self.query_one("#operator", Input).value.strip()
        try:
            if event.button.id == "start":
                credentials = await self._ensure_credentials_for_start(station_id)
                operator = self.query_one("#operator", Input).value.strip()
                run = self.orchestrator.request_run(
                    station_id,
                    package_name,
                    operator,
                    credentials=credentials,
                )
                log.write_line(f"Queued {run.run_id}")
                if credentials is not None:
                    log.write_line(f"Using cached Windows credentials for {station_id}")
                self._refresh_views()
                self._ensure_queue_processor()
                await self._drain_queue()
                log.write_line(f"Finished {run.run_id} with {run.final_status}")
            elif event.button.id == "cancel":
                if self.orchestrator.active:
                    run_id = self.orchestrator.active[-1].run_id
                    self.orchestrator.cancel_run(run_id, operator)
                    log.write_line(f"Cancellation requested for {run_id}")
                elif self.orchestrator.queue:
                    run_id = self.orchestrator.queue[-1].run_id
                    self.orchestrator.cancel_run(run_id, operator)
                    log.write_line(f"Queued run cancelled: {run_id}")
                else:
                    log.write_line("No run available to cancel")
            elif event.button.id == "dry-run":
                plan = await self.orchestrator.dry_run(station_id, package_name)
                test_names = [item["test_name"] for item in plan["plan"]]
                log.write_line(f"Dry run plan: {test_names}")
        except CredentialPromptCancelledError:
            self._set_unauthenticated_session("Windows login is still required. Start will prompt again when needed.")
            log.write_line("Credential prompt cancelled")
        except WindowsCredentialPromptUnavailableError:
            self._set_unauthenticated_session("Windows credential prompt is unavailable. Start will use configured WinRM settings.")
            log.write_line("Windows credential prompt unavailable; falling back to configured WinRM environment settings")
            if event.button.id == "start":
                run = self.orchestrator.request_run(station_id, package_name, operator)
                log.write_line(f"Queued {run.run_id}")
                self._refresh_views()
                self._ensure_queue_processor()
                await self._drain_queue()
                log.write_line(f"Finished {run.run_id} with {run.final_status}")
        except Exception as exc:
            log.write_line(f"{type(exc).__name__}: {exc}")
        finally:
            self._refresh_views()

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id == "scripts-list":
            if not self._has_widget("#scripts-detail"):
                return
            scripts = self._list_scripts()
            if scripts and event.option_index is not None and event.option_index < len(scripts):
                self.query_one("#scripts-detail", TextArea).load_text(self._render_script_detail(scripts[event.option_index][0]))
        elif event.option_list.id == "history-list":
            if not self._has_widget("#history-detail"):
                return
            paths = self._list_json_files("reports")
            if paths and event.option_index is not None and event.option_index < len(paths):
                self.query_one("#history-detail", TextArea).load_text(self._render_json_detail(paths[event.option_index]))
        elif event.option_list.id == "audit-list":
            if not self._has_widget("#audit-detail"):
                return
            paths = self._list_json_files("audit")
            if paths and event.option_index is not None and event.option_index < len(paths):
                self.query_one("#audit-detail", TextArea).load_text(self._render_json_detail(paths[event.option_index]))

    def _has_widget(self, selector: str) -> bool:
        try:
            self.query_one(selector)
        except NoMatches:
            return False
        return True
