from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.models.slice_info import SliceInfo, SliceIssue


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
    folder_label: str = "slices_original"

    def __post_init__(self) -> None:
        if not 0 <= self.png_compress_level <= 9:
            raise ValueError("PNG compression level must be between 0 and 9.")
        if not self.folder_label.strip():
            raise ValueError("Output folder label cannot be empty.")


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

    @property
    def success(self) -> bool:
        return self.status == "completed" and not self.failures
