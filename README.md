# TxTest

TxTest is a Windows-first Python 3.12 project for running diagnostic PowerShell test packages against remote Windows hosts over WinRM. The implementation is intentionally practical: it provides validated configuration, script manifests, retry-aware orchestration, JSON reporting, audit logging, persisted queue state, and a minimal Textual TUI.

## Running

```powershell
python -m pip install -e .[dev]
python -m txtest
```
