from __future__ import annotations

import csv
import json
from pathlib import Path

from jinja2 import Template

from txtest.models.domain import PackageRunReport
from txtest.utils import atomic_write_json, atomic_write_text


class ReportService:
    def __init__(self, reports_dir: Path) -> None:
        self.reports_dir = reports_dir
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def write_json(self, report: PackageRunReport) -> Path:
        path = self.reports_dir / f"{report.run_id}.json"
        atomic_write_json(path, report.model_dump(mode="json"))
        return path

    def write_csv(self, report: PackageRunReport) -> Path:
        path = self.reports_dir / f"{report.run_id}.csv"
        rows = [result.model_dump(mode="json") for result in report.results]
        fieldnames = ["test_name", "status", "message", "value", "duration_ms", "error_code", "severity", "script_version", "attempt_no"]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key) for key in fieldnames})
        return path

    def write_html(self, report: PackageRunReport) -> Path:
        path = self.reports_dir / f"{report.run_id}.html"
        template = Template(
            """
            <html><body>
            <h1>{{ report.package_name }} on {{ report.station_name }}</h1>
            <p>Final status: {{ report.final_status }}</p>
            <pre>{{ payload }}</pre>
            </body></html>
            """
        )
        payload = report.model_dump(mode="json")
        html = template.render(report=payload, payload=json.dumps(payload, indent=2))
        atomic_write_text(path, html)
        return path
