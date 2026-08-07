from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from PIL import Image, ImageChops

from app.models.composite_result import CompositeResult
from app.models.export_result import ExportedSlice, ExportFailure
from app.models.scale_plan import MappedSlice
from app.models.slice_info import SliceInfo
from app.models.validation_report import ValidationFinding, ValidationReport
from app.utils.image_modes import image_has_alpha


def _overlap(
    first: SliceInfo,
    second: SliceInfo,
) -> tuple[int, int, int, int] | None:
    left = max(first.left, second.left)
    top = max(first.top, second.top)
    right = min(first.right, second.right)
    bottom = min(first.bottom, second.bottom)
    if left < right and top < bottom:
        return left, top, right, bottom
    return None


def validate_slice_layout(
    slices: Sequence[SliceInfo],
    *,
    canvas_width: int,
    canvas_height: int,
) -> ValidationReport:
    findings: list[ValidationFinding] = []
    for item in slices:
        if item.width <= 0 or item.height <= 0:
            findings.append(
                ValidationFinding(
                    phase="preflight",
                    code="non_positive_size",
                    severity="error",
                    message="Slice has a non-positive width or height.",
                    slice_indices=(item.index,),
                    coordinates=item.bounds,
                )
            )
        elif not (
            0 <= item.left < item.right <= canvas_width
            and 0 <= item.top < item.bottom <= canvas_height
        ):
            findings.append(
                ValidationFinding(
                    phase="preflight",
                    code="out_of_canvas",
                    severity="error",
                    message="Slice extends outside the document canvas.",
                    slice_indices=(item.index,),
                    coordinates=item.bounds,
                )
            )

    for position, first in enumerate(slices):
        for second in slices[position + 1 :]:
            intersection = _overlap(first, second)
            if intersection is None:
                continue
            code = (
                "duplicate_bounds"
                if first.bounds == second.bounds
                else "overlap"
            )
            findings.append(
                ValidationFinding(
                    phase="preflight",
                    code=code,
                    severity="warning",
                    message="Slices overlap and require user review.",
                    slice_indices=(first.index, second.index),
                    coordinates=intersection,
                )
            )

    full_width = [
        item for item in slices if item.left == 0 and item.right == canvas_width
    ]
    if len(full_width) == len(slices) and full_width:
        ordered = sorted(full_width, key=lambda item: (item.top, item.index))
        cursor = 0
        for item in ordered:
            if item.top > cursor:
                findings.append(
                    ValidationFinding(
                        phase="preflight",
                        code="vertical_gap",
                        severity="warning",
                        message="Full-width slices leave an uncovered Y range.",
                        slice_indices=(item.index,),
                        coordinates=(cursor, item.top),
                    )
                )
            cursor = max(cursor, item.bottom)
        if cursor < canvas_height:
            findings.append(
                ValidationFinding(
                    phase="preflight",
                    code="vertical_gap",
                    severity="warning",
                    message="Full-width slices do not reach the canvas bottom.",
                    coordinates=(cursor, canvas_height),
                )
            )

    return ValidationReport(tuple(findings))


def _images_differ(first: Image.Image, second: Image.Image) -> bool:
    if first.mode != second.mode or first.size != second.size:
        return True
    difference = ImageChops.difference(first, second)
    try:
        extrema = difference.getextrema()
        if extrema and isinstance(extrema[0], int):
            return extrema[1] > 0
        return any(maximum > 0 for minimum, maximum in extrema)
    finally:
        difference.close()


def validate_export_outputs(
    mapped_slices: Sequence[MappedSlice],
    exported_slices: Sequence[ExportedSlice],
    failures: Sequence[ExportFailure],
    *,
    composite: CompositeResult,
    original_size: bool,
    exact_pixel_compare: bool | None = None,
    expected_format: str | None = None,
    expected_icc_profile: bytes | None = None,
    check_icc_profile: bool = False,
    expected_alpha: bool | None = None,
    cancel_check: Callable[[], bool] | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> ValidationReport:
    if exact_pixel_compare is None:
        exact_pixel_compare = original_size
    findings: list[ValidationFinding] = []
    exported_by_index = {
        item.slice_info.index: item for item in exported_slices
    }
    if len(exported_slices) != len(mapped_slices):
        findings.append(
            ValidationFinding(
                phase="post_export",
                code="output_count_mismatch",
                severity="error",
                message=(
                    f"Expected {len(mapped_slices)} files but exported "
                    f"{len(exported_slices)}."
                ),
            )
        )
    for failure in failures:
        findings.append(
            ValidationFinding(
                phase="post_export",
                code="slice_export_failed",
                severity="error",
                message=failure.message,
                slice_indices=(
                    (failure.slice_info.index,)
                    if failure.slice_info is not None
                    else ()
                ),
            )
        )

    for position, mapped in enumerate(mapped_slices, start=1):
        if cancel_check is not None and cancel_check():
            findings.append(
                ValidationFinding(
                    phase="post_export",
                    code="validation_cancelled",
                    severity="warning",
                    message=(
                        "Output validation was stopped because cancellation "
                        "was requested."
                    ),
                )
            )
            break
        if progress_callback is not None:
            progress_callback(position, len(mapped_slices))
        exported = exported_by_index.get(mapped.slice_info.index)
        if exported is None:
            continue
        path = Path(exported.output_path)
        if not path.is_file() or path.stat().st_size <= 0:
            findings.append(
                ValidationFinding(
                    phase="post_export",
                    code="missing_or_empty_file",
                    severity="error",
                    message="Exported file is missing or empty.",
                    slice_indices=(mapped.slice_info.index,),
                )
            )
            continue
        try:
            with Image.open(path) as image:
                image.load()
                if (
                    expected_format is not None
                    and image.format != expected_format
                ):
                    findings.append(
                        ValidationFinding(
                            phase="post_export",
                            code="format_mismatch",
                            severity="error",
                            message=(
                                f"Exported format is {image.format}; expected "
                                f"{expected_format}."
                            ),
                            slice_indices=(mapped.slice_info.index,),
                        )
                    )
                if image.size != (mapped.width, mapped.height):
                    findings.append(
                        ValidationFinding(
                            phase="post_export",
                            code="dimension_mismatch",
                            severity="error",
                            message="Exported dimensions do not match mapping.",
                            slice_indices=(mapped.slice_info.index,),
                        )
                    )
                if (
                    expected_format == "JPEG"
                    and image.mode != "RGB"
                ):
                    findings.append(
                        ValidationFinding(
                            phase="post_export",
                            code="jpeg_mode_mismatch",
                            severity="error",
                            message="Exported JPEG is not RGB.",
                            slice_indices=(mapped.slice_info.index,),
                        )
                    )
                if (
                    expected_alpha is not None
                    and image_has_alpha(image) != expected_alpha
                ):
                    findings.append(
                        ValidationFinding(
                            phase="post_export",
                            code="alpha_mismatch",
                            severity="error",
                            message=(
                                "Exported alpha-channel behavior does not "
                                "match the encoding plan."
                            ),
                            slice_indices=(mapped.slice_info.index,),
                        )
                    )
                if (
                    check_icc_profile
                    and image.info.get("icc_profile")
                    != expected_icc_profile
                ):
                    findings.append(
                        ValidationFinding(
                            phase="post_export",
                            code="icc_profile_mismatch",
                            severity="error",
                            message=(
                                "Exported ICC profile does not match the "
                                "encoding plan."
                            ),
                            slice_indices=(mapped.slice_info.index,),
                        )
                    )
                extrema = image.getextrema()
                band_extrema = (
                    (extrema,)
                    if extrema and isinstance(extrema[0], int)
                    else extrema
                )
                if image_has_alpha(image):
                    if "A" in image.getbands():
                        alpha_index = image.getbands().index("A")
                        alpha_extrema = band_extrema[alpha_index]
                    else:
                        rgba = image.convert("RGBA")
                        try:
                            alpha_extrema = rgba.getchannel("A").getextrema()
                        finally:
                            rgba.close()
                else:
                    alpha_extrema = None
                if alpha_extrema is not None and alpha_extrema[1] == 0:
                    findings.append(
                        ValidationFinding(
                            phase="post_export",
                            code="fully_transparent",
                            severity="warning",
                            message="Exported slice is fully transparent.",
                            slice_indices=(mapped.slice_info.index,),
                        )
                    )
                elif all(
                    low == high for low, high in band_extrema
                ):
                    findings.append(
                        ValidationFinding(
                            phase="post_export",
                            code="single_color",
                            severity="warning",
                            message="Exported slice contains one constant color.",
                            slice_indices=(mapped.slice_info.index,),
                        )
                    )

                if (
                    exact_pixel_compare
                    and composite.image is not None
                    and image.size
                    == (mapped.slice_info.width, mapped.slice_info.height)
                ):
                    expected = composite.image.crop(mapped.slice_info.bounds)
                    try:
                        if _images_differ(image, expected):
                            findings.append(
                                ValidationFinding(
                                    phase="post_export",
                                    code="pixel_mismatch",
                                    severity="error",
                                    message=(
                                        "Lossless original-size output pixels "
                                        "differ from the embedded composite."
                                    ),
                                    slice_indices=(mapped.slice_info.index,),
                                )
                            )
                    finally:
                        expected.close()
        except Exception as error:
            findings.append(
                ValidationFinding(
                    phase="post_export",
                    code="image_reopen_failed",
                    severity="error",
                    message=f"Exported image cannot be reopened: {error}",
                    slice_indices=(mapped.slice_info.index,),
                )
            )
    return ValidationReport(tuple(findings))


def validate_full_canvas_output(
    output_path: Path,
    *,
    composite: CompositeResult,
    expected_size: tuple[int, int],
    expected_format: str,
    expected_icc_profile: bytes | None,
    expected_alpha: bool | None,
    exact_pixel_compare: bool = False,
    cancel_check: Callable[[], bool] | None = None,
) -> ValidationReport:
    """Validate one complete-canvas image independently of slice metadata."""

    findings: list[ValidationFinding] = []
    if cancel_check is not None and cancel_check():
        return ValidationReport(
            (
                ValidationFinding(
                    phase="post_export",
                    code="validation_cancelled",
                    severity="warning",
                    message=(
                        "Output validation was stopped because cancellation "
                        "was requested."
                    ),
                ),
            )
        )
    if not output_path.is_file() or output_path.stat().st_size <= 0:
        return ValidationReport(
            (
                ValidationFinding(
                    phase="post_export",
                    code="missing_or_empty_file",
                    severity="error",
                    message="Complete-canvas output is missing or empty.",
                ),
            )
        )

    try:
        with Image.open(output_path) as image:
            image.load()
            if image.format != expected_format:
                findings.append(
                    ValidationFinding(
                        phase="post_export",
                        code="format_mismatch",
                        severity="error",
                        message=(
                            f"Exported format is {image.format}; expected "
                            f"{expected_format}."
                        ),
                    )
                )
            if image.size != expected_size:
                findings.append(
                    ValidationFinding(
                        phase="post_export",
                        code="dimension_mismatch",
                        severity="error",
                        message=(
                            "Complete-canvas output dimensions do not match "
                            "the requested target."
                        ),
                        coordinates=(
                            expected_size[0],
                            expected_size[1],
                            image.width,
                            image.height,
                        ),
                    )
                )
            if expected_format == "JPEG" and image.mode != "RGB":
                findings.append(
                    ValidationFinding(
                        phase="post_export",
                        code="jpeg_mode_mismatch",
                        severity="error",
                        message="Exported JPEG is not RGB.",
                    )
                )
            if (
                expected_alpha is not None
                and image_has_alpha(image) != expected_alpha
            ):
                findings.append(
                    ValidationFinding(
                        phase="post_export",
                        code="alpha_mismatch",
                        severity="error",
                        message=(
                            "Exported alpha-channel behavior does not match "
                            "the encoding plan."
                        ),
                    )
                )
            if (
                image.info.get("icc_profile") != expected_icc_profile
            ):
                findings.append(
                    ValidationFinding(
                        phase="post_export",
                        code="icc_profile_mismatch",
                        severity="error",
                        message=(
                            "Exported ICC profile does not match the "
                            "encoding plan."
                        ),
                    )
                )
            extrema = image.getextrema()
            band_extrema = (
                (extrema,)
                if extrema and isinstance(extrema[0], int)
                else extrema
            )
            if image_has_alpha(image) and "A" in image.getbands():
                alpha_index = image.getbands().index("A")
                alpha_extrema = band_extrema[alpha_index]
                if alpha_extrema[1] == 0:
                    findings.append(
                        ValidationFinding(
                            phase="post_export",
                            code="fully_transparent",
                            severity="warning",
                            message="Complete-canvas output is fully transparent.",
                        )
                    )
            elif band_extrema and all(
                low == high for low, high in band_extrema
            ):
                findings.append(
                    ValidationFinding(
                        phase="post_export",
                        code="single_color",
                        severity="warning",
                        message="Complete-canvas output contains one constant color.",
                    )
                )

            if (
                exact_pixel_compare
                and composite.image is not None
                and image.size == composite.image.size
                and _images_differ(image, composite.image)
            ):
                findings.append(
                    ValidationFinding(
                        phase="post_export",
                        code="pixel_mismatch",
                        severity="error",
                        message=(
                            "Lossless original-size output pixels differ "
                            "from the embedded composite."
                        ),
                    )
                )
    except Exception as error:
        findings.append(
            ValidationFinding(
                phase="post_export",
                code="image_reopen_failed",
                severity="error",
                message=f"Complete-canvas output cannot be reopened: {error}",
            )
        )
    return ValidationReport(tuple(findings))
