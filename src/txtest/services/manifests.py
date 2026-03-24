from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from txtest.models import ManifestDefinition


def discover_manifests(scripts_dir: Path) -> dict[str, ManifestDefinition]:
    manifests: dict[str, ManifestDefinition] = {}
    for path in sorted(scripts_dir.glob("*.manifest.yaml")):
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        try:
            manifest = ManifestDefinition.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(f"Manifest '{path.name}' is invalid: {exc}") from exc
        script_path = scripts_dir / manifest.script_file
        if not script_path.exists():
            raise ValueError(f"Manifest '{path.name}' references missing script '{manifest.script_file}'")
        manifests[path.name] = manifest
    return manifests


def validate_package_manifest_links(package_manifest_names: list[str], discovered: dict[str, ManifestDefinition]) -> None:
    for manifest_name in package_manifest_names:
        if manifest_name not in discovered:
            raise ValueError(f"Package references unknown manifest '{manifest_name}'")
