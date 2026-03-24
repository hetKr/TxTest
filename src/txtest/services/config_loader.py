from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import ValidationError

from txtest.models.core import AppConfig
from txtest.models.domain import PackagesConfig, ScriptManifest, StationsConfig


class ConfigCompatibilityError(ValueError):
    pass


class ConfigLoader:
    def load_yaml(self, path: Path) -> dict:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    def load_stations(self, path: Path) -> StationsConfig:
        payload = self.load_yaml(path)
        try:
            return StationsConfig.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

    def load_packages(self, path: Path) -> PackagesConfig:
        payload = self.load_yaml(path)
        try:
            return PackagesConfig.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

    def load_manifest(self, path: Path) -> ScriptManifest:
        payload = self.load_yaml(path)
        try:
            return ScriptManifest.model_validate(payload)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

    def load_app_config(self, stations_path: Path, packages_path: Path) -> AppConfig:
        stations = self.load_stations(stations_path)
        packages = self.load_packages(packages_path)
        if stations.schema_version != packages.schema_version:
            raise ConfigCompatibilityError("stations.yaml and packages.yaml must use the same schema_version")
        return AppConfig(
            schema_version=stations.schema_version,
            stations=stations.stations,
            packages=packages.packages,
            max_parallel_stations=self.load_yaml(packages_path).get("max_parallel_stations", 3),
        )
