from __future__ import annotations

import json
from pathlib import Path

from txtest.models import AuditEntry
from txtest.utils import atomic_write_json


class AuditService:
    def __init__(self, audit_dir: Path) -> None:
        self.audit_dir = audit_dir
        self.audit_dir.mkdir(parents=True, exist_ok=True)

    def record(self, entry: AuditEntry) -> Path:
        path = self.audit_dir / f"{entry.audit_id}.json"
        atomic_write_json(path, entry.model_dump(mode="json"))
        return path


def append_audit_entry(path: Path, entry: AuditEntry) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing: list[dict] = []
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
    existing.append(entry.model_dump(mode="json"))
    atomic_write_json(path, existing)
    return path
