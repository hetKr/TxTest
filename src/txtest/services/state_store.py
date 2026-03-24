from __future__ import annotations

from pathlib import Path

from txtest.models.domain import QueueRun
from txtest.utils import atomic_write_json


class QueueStateStore:
    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.state_dir / "queue_state.json"

    def save(self, queue: list[QueueRun]) -> Path:
        atomic_write_json(self.path, [item.model_dump(mode="json") for item in queue])
        return self.path
