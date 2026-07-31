from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.models.scale_plan import ResizeStrategy
from app.models.slice_info import SliceInfo, SliceIssue
from app.models.validation_report import ValidationReport


ExportStatus = Literal["completed", "completed_with_errors", "cancelled"]
ProgressPhase = Literal["starting", "exporting", "written", "archiving"]


@dataclass(frozen=True, slots=True)
class ExportOptions:
    """Options supported by the original-size PNG export stage."""

    output_parent: Path | None = None
    create_zip: bool = False
    allow_unverified_composite: bool = False
    selected_slice_indices: frozenset[int] | None = None
    png_compress_level: int = 6
    folder_label: str | None = None
    target_width: int | None = None
    allow_upscale: bool = True
    max_full_resize_bytes: int = 512 * 1024 * 1024
    resize_edge_padding: int = 8
    write_validation_reports: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.png_compress_level <= 9:
            raise ValueError("PNG compression level must be between 0 and 9.")
        if self.folder_label is not None and not self.folder_label.strip():
            raise ValueError("Output folder label cannot be empty.")
        if self.target_width is not None and self.target_width <= 0:
            raise ValueError("Target width must be a positive integer.")
        if self.max_full_resize_bytes <= 0:
            raise ValueError("Full-resize memory limit must be positive.")
        if self.resize_edge_padding < 0:
            raise ValueError("Resize edge padding cannot be negative.")


@dataclass(frozen=True, slots=True)
class ExportProgress:
    phase: ProgressPhase
    current: int
    total: int
    slice_info: SliceInfo | None = None
    output_path: Path | None = None


@dataclass(frozen=True, slots=True)
class ExportedSlice:
    slice_info: SliceInfo
    output_path: Path
    width: int
    height: int
    mode: str
    file_size: int


@dataclass(frozen=True, slots=True)
class ExportFailure:
    message: str
    slice_info: SliceInfo | None = None
    output_path: Path | None = None
    exception_type: str | None = None


@dataclass(frozen=True, slots=True)
class ExportResult:
    source_path: Path
    output_directory: Path
    archive_path: Path | None
    status: ExportStatus
    exported_slices: tuple[ExportedSlice, ...]
    failures: tuple[ExportFailure, ...]
    slice_issues: tuple[SliceIssue, ...]
    composite_warning: str | None
    source_unchanged: bool
    elapsed_seconds: float
    target_width: int
    scale: float
    resize_strategy: ResizeStrategy
    validation_report: ValidationReport
    validation_json_path: Path | None
    validation_text_path: Path | None

    @property
    def success(self) -> bool:
        return self.status == "completed" and not self.failures
