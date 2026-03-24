from __future__ import annotations

from pathlib import Path

from txtest.models.domain import ScriptManifest, SUPPORTED_SCHEMA_VERSIONS
from txtest.services.config_loader import ConfigLoader


class PluginLoader:
    def __init__(self, loader: ConfigLoader | None = None) -> None:
        self.loader = loader or ConfigLoader()

    def discover(self, scripts_dir: Path) -> dict[str, ScriptManifest]:
        manifests: dict[str, ScriptManifest] = {}
        for path in sorted(scripts_dir.glob("*.manifest.yaml")):
            manifest = self.loader.load_manifest(path)
            if manifest.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
                raise ValueError(f"Unsupported manifest schema version: {manifest.schema_version}")
            manifests[manifest.name] = manifest
        return manifests
