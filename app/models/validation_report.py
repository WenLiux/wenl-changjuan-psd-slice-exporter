from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from app.config.brand import (
    BRAND_NAME,
    FULL_PRODUCT_NAME,
    FUNCTIONAL_SLOGAN,
    VERSION,
)


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
            "product": FULL_PRODUCT_NAME,
            "brand": BRAND_NAME,
            "version": VERSION,
            "passed": self.passed,
            "warning_count": self.warning_count,
            "error_count": self.error_count,
            "findings": [asdict(item) for item in self.findings],
        }

    def to_text(self) -> str:
        lines = [
            BRAND_NAME,
            "高保真切片导出验证报告",
            "=" * 32,
            f"版本：{VERSION}",
            f"验证结果：{'通过' if self.passed else '未通过'}",
            f"警告：{self.warning_count}",
            f"错误：{self.error_count}",
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
        lines.extend(["", FUNCTIONAL_SLOGAN])
        return "\n".join(lines) + "\n"

    def write(self, output_directory: Path) -> tuple[Path, Path]:
        json_path = output_directory / "WENL长卷_导出验证报告.json"
        text_path = output_directory / "WENL长卷_导出验证报告.txt"
        json_path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        text_path.write_text(self.to_text(), encoding="utf-8")
        return json_path, text_path
