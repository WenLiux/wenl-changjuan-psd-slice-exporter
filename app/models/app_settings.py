from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal


WidthMode = Literal["original", "custom"]
ExportMode = Literal["slices", "full_canvas"]
OutputFormat = Literal["png", "jpeg"]
ColorPolicy = Literal["auto", "preserve", "srgb"]
NamingRule = Literal[
    "sequence_dimensions",
    "slice_name",
    "slice_name_with_index",
]
PhotoshopFallbackMode = Literal["disabled", "if_needed", "always"]


@dataclass(frozen=True, slots=True)
class AppSettings:
    """Validated user preferences for the desktop exporter."""

    output_directory: Path | None = None
    export_mode: ExportMode = "slices"
    width_mode: WidthMode = "original"
    target_width: int = 1440
    allow_upscale: bool = True
    output_format: OutputFormat = "png"
    jpeg_quality: int = 95
    jpeg_background: str = "#FFFFFF"
    color_policy: ColorPolicy = "auto"
    create_zip: bool = False
    open_output_folder: bool = True
    naming_rule: NamingRule = "sequence_dimensions"
    photoshop_fallback: PhotoshopFallbackMode = "disabled"

    def __post_init__(self) -> None:
        if self.output_directory is not None and not isinstance(
            self.output_directory,
            Path,
        ):
            raise TypeError("Output directory must be a Path or None.")
        if self.export_mode not in {"slices", "full_canvas"}:
            raise ValueError("Export mode must be slices or full_canvas.")
        if self.width_mode not in {"original", "custom"}:
            raise ValueError("Width mode must be original or custom.")
        if (
            isinstance(self.target_width, bool)
            or not isinstance(self.target_width, int)
            or self.target_width <= 0
        ):
            raise ValueError("Target width must be a positive integer.")
        if not isinstance(self.allow_upscale, bool):
            raise TypeError("Allow upscale must be a boolean.")
        if self.output_format not in {"png", "jpeg"}:
            raise ValueError("Output format must be png or jpeg.")
        if (
            isinstance(self.jpeg_quality, bool)
            or not isinstance(self.jpeg_quality, int)
            or not 1 <= self.jpeg_quality <= 100
        ):
            raise ValueError("JPEG quality must be between 1 and 100.")
        if (
            not isinstance(self.jpeg_background, str)
            or len(self.jpeg_background) != 7
            or not self.jpeg_background.startswith("#")
        ):
            raise ValueError(
                "JPEG background must use #RRGGBB hexadecimal notation."
            )
        try:
            int(self.jpeg_background[1:], 16)
        except ValueError as error:
            raise ValueError(
                "JPEG background must use #RRGGBB hexadecimal notation."
            ) from error
        if self.color_policy not in {"auto", "preserve", "srgb"}:
            raise ValueError(
                "Color policy must be auto, preserve, or srgb."
            )
        if not isinstance(self.create_zip, bool):
            raise TypeError("Create ZIP must be a boolean.")
        if not isinstance(self.open_output_folder, bool):
            raise TypeError("Open output folder must be a boolean.")
        if self.naming_rule not in {
            "sequence_dimensions",
            "slice_name",
            "slice_name_with_index",
        }:
            raise ValueError(
                "Naming rule must be sequence_dimensions, slice_name, "
                "or slice_name_with_index."
            )
        if self.photoshop_fallback not in {
            "disabled",
            "if_needed",
            "always",
        }:
            raise ValueError(
                "Photoshop fallback must be disabled, if_needed, or always."
            )
