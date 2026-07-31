from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal


ValidationSeverity = Literal["info", "warning", "error"]
ValidationPhase = Literal["preflight", "post_export"]


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    phase: ValidationPhase
    code: str
    severity: ValidationSeverity
    message: str
    slice_indices: tuple[int, ...] = ()
    coordinates: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class ValidationReport:
    findings: tuple[ValidationFinding, ...]

    @property
    def passed(self) -> bool:
        return not any(item.severity == "error" for item in self.findings)

    @property
    def warning_count(self) -> int:
        return sum(item.severity == "warning" for item in self.findings)

    @property
    def error_count(self) -> int:
        return sum(item.severity == "error" for item in self.findings)

    def merged(self, other: ValidationReport) -> ValidationReport:
        return ValidationReport(self.findings + other.findings)

    def to_dict(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "warning_count": self.warning_count,
            "error_count": self.error_count,
            "findings": [asdict(item) for item in self.findings],
        }

    def to_text(self) -> str:
        lines = [
            f"Validation: {'PASS' if self.passed else 'FAIL'}",
            f"Warnings: {self.warning_count}",
            f"Errors: {self.error_count}",
        ]
        for item in self.findings:
            slices = (
                f" slices={','.join(map(str, item.slice_indices))}"
                if item.slice_indices
                else ""
            )
            coordinates = (
                f" coordinates={','.join(map(str, item.coordinates))}"
                if item.coordinates
                else ""
            )
            lines.append(
                f"[{item.severity.upper()}] {item.phase}/{item.code}: "
                f"{item.message}{slices}{coordinates}"
            )
        return "\n".join(lines) + "\n"

    def write(self, output_directory: Path) -> tuple[Path, Path]:
        json_path = output_directory / "validation_report.json"
        text_path = output_directory / "validation_report.txt"
        json_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        text_path.write_text(self.to_text(), encoding="utf-8")
        return json_path, text_path
