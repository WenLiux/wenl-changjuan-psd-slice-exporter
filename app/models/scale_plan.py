from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.models.slice_info import SliceInfo


ResizeStrategy = Literal["none", "full_canvas", "per_slice"]


@dataclass(frozen=True, slots=True)
class MappedSlice:
    slice_info: SliceInfo
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        return self.left, self.top, self.right, self.bottom


@dataclass(frozen=True, slots=True)
class ScalePlan:
    source_width: int
    source_height: int
    output_width: int
    output_height: int
    scale: float
    mapped_slices: tuple[MappedSlice, ...]

    @property
    def is_original_size(self) -> bool:
        return self.output_width == self.source_width

    @property
    def estimated_rgba_bytes(self) -> int:
        return self.output_width * self.output_height * 4
