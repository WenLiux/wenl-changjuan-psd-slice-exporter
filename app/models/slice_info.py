from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


IssueSeverity = Literal["warning", "error"]


@dataclass(frozen=True, slots=True)
class SliceInfo:
    """One normalized Photoshop slice record."""

    index: int
    slice_id: int | None
    name: str
    left: int
    top: int
    right: int
    bottom: int
    is_automatic: bool
    source_version: str
    origin: str | int | None = None
    slice_type: str | int | None = None

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.right, self.bottom

    def covers_canvas(self, canvas_width: int, canvas_height: int) -> bool:
        return self.bounds == (0, 0, canvas_width, canvas_height)


@dataclass(frozen=True, slots=True)
class SliceIssue:
    """A parser or normalization issue suitable for UI presentation."""

    code: str
    message: str
    severity: IssueSeverity = "warning"
    slice_index: int | None = None
    slice_id: int | None = None


@dataclass(frozen=True, slots=True)
class SliceParseResult:
    """Normalized slices plus explicit exclusions and warnings."""

    source_version: str
    all_slices: tuple[SliceInfo, ...]
    exportable_slices: tuple[SliceInfo, ...]
    excluded_slices: tuple[SliceInfo, ...]
    issues: tuple[SliceIssue, ...]

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.issues)
