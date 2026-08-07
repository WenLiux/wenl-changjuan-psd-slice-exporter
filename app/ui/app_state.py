from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

from app.core.resizer import ResizePlanError, build_scale_plan
from app.models.app_settings import AppSettings
from app.models.export_result import ExportOptions
from app.models.prepared_document import DocumentSummary
from app.models.slice_info import SliceInfo


class UiMode(StrEnum):
    """Top-level desktop UI modes.

    These values deliberately contain no widget state so the event loop can
    translate them into enabled/disabled controls in one place.
    """

    EMPTY = "empty"
    LOADING = "loading"
    READY = "ready"
    EXPORTING = "exporting"
    CANCELLING = "cancelling"
    SHUTTING_DOWN = "shutting_down"

    @property
    def is_busy(self) -> bool:
        return self in {
            UiMode.LOADING,
            UiMode.EXPORTING,
            UiMode.CANCELLING,
            UiMode.SHUTTING_DOWN,
        }

    @property
    def can_cancel(self) -> bool:
        return self in {UiMode.LOADING, UiMode.EXPORTING}


class FormValidationError(ValueError):
    """A user-correctable export form error."""


@dataclass(frozen=True, slots=True)
class OutputFormatUiState:
    """Widget-independent state needed to link PNG and JPEG controls."""

    output_format: Literal["png", "jpeg"]
    file_extension: str
    jpeg_quality_enabled: bool
    jpeg_background_enabled: bool
    supports_transparency: bool

    @property
    def is_png(self) -> bool:
        return self.output_format == "png"

    @property
    def is_jpeg(self) -> bool:
        return self.output_format == "jpeg"


@dataclass(frozen=True, slots=True)
class SliceOutputEstimate:
    """Expected output dimensions for one source slice."""

    slice_info: SliceInfo
    output_width: int
    output_height: int

    @property
    def index(self) -> int:
        """Return the parser index, which is not necessarily sequential."""

        return self.slice_info.index

    @property
    def source_width(self) -> int:
        return self.slice_info.width

    @property
    def source_height(self) -> int:
        return self.slice_info.height


_HEX_RGB_PATTERN = re.compile(r"#[0-9A-Fa-f]{6}\Z")


def parse_hex_rgb(value: str) -> tuple[int, int, int]:
    """Parse a UI ``#RRGGBB`` value into the exporter's RGB tuple."""

    if not isinstance(value, str):
        raise FormValidationError(
            "JPEG background must use #RRGGBB hexadecimal notation."
        )
    normalized = value.strip()
    if _HEX_RGB_PATTERN.fullmatch(normalized) is None:
        raise FormValidationError(
            "JPEG background must use #RRGGBB hexadecimal notation."
        )
    return tuple(
        int(normalized[offset : offset + 2], 16)
        for offset in (1, 3, 5)
    )


def derive_output_format_state(
    output_format: str,
) -> OutputFormatUiState:
    """Return all PNG/JPEG control linkage without referring to Tk."""

    normalized = output_format.strip().lower()
    if normalized == "jpg":
        normalized = "jpeg"
    if normalized == "png":
        return OutputFormatUiState(
            output_format="png",
            file_extension=".png",
            jpeg_quality_enabled=False,
            jpeg_background_enabled=False,
            supports_transparency=True,
        )
    if normalized == "jpeg":
        return OutputFormatUiState(
            output_format="jpeg",
            file_extension=".jpg",
            jpeg_quality_enabled=True,
            jpeg_background_enabled=True,
            supports_transparency=False,
        )
    raise FormValidationError("Output format must be PNG or JPEG.")


def estimate_slice_outputs(
    settings: AppSettings,
    document: DocumentSummary,
    *,
    selected_slice_indices: Iterable[int] | None = None,
) -> tuple[SliceOutputEstimate, ...]:
    """Calculate slice dimensions with the production rounding rule.

    ``None`` estimates every exportable slice. An explicitly empty selection
    returns no rows, which lets the UI render the temporary unchecked state;
    :func:`build_export_options` rejects that state before export.
    """

    selected = _normalize_slice_indices(
        selected_slice_indices,
        document,
        none_means_all=True,
        require_one=False,
    )
    selected_slices = tuple(
        item for item in document.slices if item.index in selected
    )
    plan = _build_form_scale_plan(settings, document, selected_slices)
    return tuple(
        SliceOutputEstimate(
            slice_info=mapped.slice_info,
            output_width=mapped.width,
            output_height=mapped.height,
        )
        for mapped in plan.mapped_slices
    )


def build_export_options(
    settings: AppSettings,
    document: DocumentSummary,
    *,
    output_directory: Path | str | None,
    selected_slice_indices: Iterable[int] | None,
    photoshop_allow_launch: bool = False,
    allow_mode_conversion: bool = False,
    allow_unverified_composite: bool = False,
) -> ExportOptions:
    """Validate the current form and build one immutable export request.

    The three safety flags are intentionally call arguments rather than saved
    settings. The caller must supply them again for each export attempt.
    """

    if not isinstance(settings, AppSettings):
        raise TypeError("settings must be an AppSettings instance.")
    if not isinstance(document, DocumentSummary):
        raise TypeError("document must be a DocumentSummary instance.")

    output_parent = _normalize_output_directory(
        output_directory,
        default=document.source_path.parent,
    )
    selected = (
        _normalize_slice_indices(
            selected_slice_indices,
            document,
            none_means_all=True,
            require_one=True,
        )
        if settings.export_mode == "slices"
        else None
    )
    selected_slices = tuple(
        item
        for item in document.slices
        if selected is not None and item.index in selected
    )
    if settings.export_mode == "full_canvas":
        selected_slices = ()
    _build_form_scale_plan(settings, document, selected_slices)

    _require_bool("photoshop_allow_launch", photoshop_allow_launch)
    _require_bool("allow_mode_conversion", allow_mode_conversion)
    _require_bool(
        "allow_unverified_composite",
        allow_unverified_composite,
    )

    return ExportOptions(
        output_parent=output_parent,
        export_mode=settings.export_mode,
        create_zip=settings.create_zip,
        allow_unverified_composite=allow_unverified_composite,
        selected_slice_indices=selected,
        output_format=settings.output_format,
        jpeg_quality=settings.jpeg_quality,
        jpeg_background=parse_hex_rgb(settings.jpeg_background),
        color_policy=settings.color_policy,
        allow_mode_conversion=allow_mode_conversion,
        photoshop_fallback=settings.photoshop_fallback,
        photoshop_allow_launch=photoshop_allow_launch,
        naming_rule=settings.naming_rule,
        target_width=_effective_target_width(settings),
        allow_upscale=settings.allow_upscale,
    )


def _effective_target_width(settings: AppSettings) -> int | None:
    if settings.width_mode == "original":
        return None
    target_width = settings.target_width
    if (
        isinstance(target_width, bool)
        or not isinstance(target_width, int)
        or target_width <= 0
    ):
        raise FormValidationError(
            "Target width must be a positive integer."
        )
    return target_width


def _build_form_scale_plan(
    settings: AppSettings,
    document: DocumentSummary,
    slices: tuple[SliceInfo, ...],
):
    try:
        return build_scale_plan(
            canvas_width=document.width,
            canvas_height=document.height,
            slices=slices,
            target_width=_effective_target_width(settings),
            allow_upscale=settings.allow_upscale,
        )
    except ResizePlanError as error:
        raise FormValidationError(str(error)) from error


def _normalize_output_directory(
    value: Path | str | None,
    *,
    default: Path,
) -> Path:
    if value is None:
        path = default
    elif isinstance(value, str):
        path = Path(value.strip()) if value.strip() else default
    elif isinstance(value, Path):
        path = value
    else:
        raise FormValidationError("Choose a valid output directory.")
    if path.exists() and not path.is_dir():
        raise FormValidationError(
            "The selected output path is not a directory."
        )
    return path


def _normalize_slice_indices(
    values: Iterable[int] | None,
    document: DocumentSummary,
    *,
    none_means_all: bool,
    require_one: bool,
) -> frozenset[int]:
    if values is None:
        selected = (
            frozenset(item.index for item in document.slices)
            if none_means_all
            else frozenset()
        )
    else:
        try:
            selected = frozenset(values)
        except TypeError as error:
            raise FormValidationError(
                "Slice selection must contain integer indices."
            ) from error

    if any(
        isinstance(index, bool) or not isinstance(index, int)
        for index in selected
    ):
        raise FormValidationError(
            "Slice selection must contain integer indices."
        )
    if require_one and not selected:
        raise FormValidationError("Select at least one slice.")

    known = {item.index for item in document.slices}
    unknown = selected - known
    if unknown:
        formatted = ", ".join(str(index) for index in sorted(unknown))
        raise FormValidationError(
            f"Unknown slice index: {formatted}."
        )
    return selected


def _require_bool(name: str, value: object) -> None:
    if not isinstance(value, bool):
        raise TypeError(f"{name} must be a boolean.")


__all__ = [
    "FormValidationError",
    "OutputFormatUiState",
    "SliceOutputEstimate",
    "UiMode",
    "build_export_options",
    "derive_output_format_state",
    "estimate_slice_outputs",
    "parse_hex_rgb",
]
