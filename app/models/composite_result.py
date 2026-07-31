from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from PIL import Image


CompositeSource = Literal[
    "embedded_merged",
    "embedded_merged_unverified",
    "photoshop",
    "missing",
    "invalid",
]


@dataclass(slots=True)
class CompositeResult:
    """Decoded Photoshop-saved merged image and its reliability metadata."""

    image: Image.Image | None
    source: CompositeSource
    width: int
    height: int
    color_mode: str
    depth: int
    pil_mode: str | None
    icc_profile: bytes | None
    has_alpha: bool
    is_reliable: bool
    warning: str | None = None
    error: str | None = None

    @property
    def is_available(self) -> bool:
        return self.image is not None

    @property
    def requires_photoshop(self) -> bool:
        return self.image is None
