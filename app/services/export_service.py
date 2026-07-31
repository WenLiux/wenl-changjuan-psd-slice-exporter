from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from PIL import Image
from psd_tools import PSDImage

from app.core.composite_reader import read_embedded_composite
from app.core.image_encoder import (
    ImageEncodingError,
    build_image_encoding_plan,
    prepare_image_for_encoding,
    save_options_for_plan,
)
from app.core.resizer import (
    ResizePlanError,
    build_scale_plan,
    resize_full_composite,
    resize_mapped_slice,
)
from app.core.slice_parser import parse_document_slices
from app.core.validator import validate_export_outputs, validate_slice_layout
from app.models.composite_result import CompositeResult
from app.models.export_result import (
    ExportedSlice,
    ExportFailure,
    ExportOptions,
    ExportProgress,
    ExportResult,
    ExportStatus,
    ProgressPhase,
)
from app.models.scale_plan import ResizeStrategy
from app.models.slice_info import SliceInfo, SliceParseResult
from app.utils.paths import create_collision_safe_directory


ProgressCallback = Callable[[ExportProgress], None]
CancelCheck = Callable[[], bool]


class ExportServiceError(RuntimeError):
    """Base class for user-facing export service errors."""


class ExportPreflightError(ExportServiceError):
    """Raised before output is created when export cannot safely proceed."""


def _source_signature(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_size, stat.st_mtime_ns


def _selected_slices(
    slice_result: SliceParseResult,
    selected_indices: frozenset[int] | None,
) -> list[SliceInfo]:
    slices = list(slice_result.exportable_slices)
    if selected_indices is None:
        return slices
    return [item for item in slices if item.index in selected_indices]


def _emit(
    callback: ProgressCallback | None,
    *,
    phase: ProgressPhase,
    current: int,
    total: int,
    slice_info: SliceInfo | None = None,
    output_path: Path | None = None,
) -> None:
    if callback is None:
        return
    callback(
        ExportProgress(
            phase=phase,
            current=current,
            total=total,
            slice_info=slice_info,
            output_path=output_path,
        )
    )


def _verify_image(
    path: Path,
    expected_size: tuple[int, int],
    expected_format: str,
) -> tuple[str, int]:
    with Image.open(path) as image:
        actual_format = image.format
        image.verify()
    if actual_format != expected_format:
        raise ValueError(
            f"Saved image format is {actual_format}; expected "
            f"{expected_format}."
        )
    with Image.open(path) as image:
        if image.size != expected_size:
            raise ValueError(
                f"Saved image size is {image.width} x {image.height}; "
                f"expected {expected_size[0]} x {expected_size[1]}."
            )
        mode = image.mode
        if expected_format == "JPEG" and mode != "RGB":
            raise ValueError(
                f"Saved JPEG mode is {mode}; expected RGB."
            )
    return mode, path.stat().st_size


def export_prepared_slices(
    source_path: Path,
    slice_result: SliceParseResult,
    composite: CompositeResult,
    options: ExportOptions,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> ExportResult:
    """Export normalized slices using one global output-width mapping."""

    if composite.image is None:
        raise ExportPreflightError(
            composite.error or "No embedded composite is available for export."
        )
    if not composite.is_reliable and not options.allow_unverified_composite:
        raise ExportPreflightError(
            composite.warning
            or "The embedded composite cannot be confirmed as complete."
        )
    if slice_result.has_errors:
        error_count = sum(
            issue.severity == "error" for issue in slice_result.issues
        )
        raise ExportPreflightError(
            f"Slice validation found {error_count} blocking error(s)."
        )

    slices = _selected_slices(
        slice_result,
        options.selected_slice_indices,
    )
    if not slices:
        raise ExportPreflightError("There are no exportable slices selected.")

    preflight_report = validate_slice_layout(
        slices,
        canvas_width=composite.width,
        canvas_height=composite.height,
    )
    if not preflight_report.passed:
        raise ExportPreflightError(
            f"Preflight validation found {preflight_report.error_count} "
            "blocking error(s)."
        )

    try:
        encoding_plan = build_image_encoding_plan(composite, options)
    except ImageEncodingError as error:
        raise ExportPreflightError(str(error)) from error

    try:
        scale_plan = build_scale_plan(
            canvas_width=composite.width,
            canvas_height=composite.height,
            slices=slices,
            target_width=options.target_width,
            allow_upscale=options.allow_upscale,
        )
    except ResizePlanError as error:
        raise ExportPreflightError(str(error)) from error

    source_path = Path(source_path)
    output_parent = options.output_parent or source_path.parent
    folder_label = options.folder_label
    if folder_label is None:
        folder_label = (
            "slices_original"
            if options.target_width is None
            else f"slices_{scale_plan.output_width}px"
        )
    source_signature_before = _source_signature(source_path)
    started = time.perf_counter()
    exported: list[ExportedSlice] = []
    failures: list[ExportFailure] = []
    archive_path: Path | None = None
    validation_json_path: Path | None = None
    validation_text_path: Path | None = None
    cancelled = False
    total = len(slices)
    resized_composite: Image.Image | None = None
    render_image: Image.Image | None
    resize_strategy: ResizeStrategy
    if scale_plan.is_original_size:
        render_image = composite.image
        resize_strategy = "none"
    elif scale_plan.estimated_rgba_bytes <= options.max_full_resize_bytes:
        try:
            resized_composite = resize_full_composite(
                composite.image,
                scale_plan,
            )
        except Exception as error:
            raise ExportPreflightError(
                f"Unable to resize the complete composite: {error}"
            ) from error
        render_image = resized_composite
        resize_strategy = "full_canvas"
    else:
        render_image = None
        resize_strategy = "per_slice"
    try:
        output_directory = create_collision_safe_directory(
            output_parent,
            f"{source_path.stem}_{folder_label}",
            reserve_zip_path=options.create_zip,
        )
    except Exception as error:
        if resized_composite is not None:
            resized_composite.close()
        raise ExportPreflightError(
            f"Unable to create the output directory: {error}"
        ) from error

    _emit(
        progress_callback,
        phase="starting",
        current=0,
        total=total,
    )

    try:
        for position, mapped_slice in enumerate(
            scale_plan.mapped_slices,
            start=1,
        ):
            slice_info = mapped_slice.slice_info
            if cancel_check is not None and cancel_check():
                cancelled = True
                break

            output_path = output_directory / (
                f"slice_{position:02d}_{mapped_slice.width}x"
                f"{mapped_slice.height}{encoding_plan.extension}"
            )
            temporary_path = output_path.with_name(f".{output_path.name}.part")
            _emit(
                progress_callback,
                phase="exporting",
                current=position,
                total=total,
                slice_info=slice_info,
                output_path=output_path,
            )

            crop: Image.Image | None = None
            encoded_image: Image.Image | None = None
            try:
                if resize_strategy == "per_slice":
                    crop = resize_mapped_slice(
                        composite.image,
                        mapped_slice,
                        scale_plan,
                        edge_padding=options.resize_edge_padding,
                    )
                else:
                    if render_image is None:
                        raise RuntimeError("Resize image is unavailable.")
                    crop = render_image.crop(mapped_slice.bounds)
                encoded_image = prepare_image_for_encoding(
                    crop,
                    encoding_plan,
                )
                save_options = save_options_for_plan(encoding_plan)
                if encoding_plan.output_format == "png":
                    save_options["compress_level"] = (
                        options.png_compress_level
                    )
                encoded_image.save(temporary_path, **save_options)
                temporary_path.replace(output_path)
                mode, file_size = _verify_image(
                    output_path,
                    (mapped_slice.width, mapped_slice.height),
                    (
                        "PNG"
                        if encoding_plan.output_format == "png"
                        else "JPEG"
                    ),
                )
                exported.append(
                    ExportedSlice(
                        slice_info=slice_info,
                        output_path=output_path,
                        width=mapped_slice.width,
                        height=mapped_slice.height,
                        mode=mode,
                        file_size=file_size,
                    )
                )
                _emit(
                    progress_callback,
                    phase="written",
                    current=position,
                    total=total,
                    slice_info=slice_info,
                    output_path=output_path,
                )
            except Exception as error:
                if temporary_path.exists():
                    temporary_path.unlink()
                failures.append(
                    ExportFailure(
                        message=(
                            f"Slice {slice_info.index} could not be exported: "
                            f"{error}"
                        ),
                        slice_info=slice_info,
                        output_path=output_path,
                        exception_type=type(error).__name__,
                    )
                )
            finally:
                if encoded_image is not None:
                    encoded_image.close()
                if crop is not None:
                    crop.close()
    finally:
        if resized_composite is not None:
            resized_composite.close()

    post_export_report = validate_export_outputs(
        scale_plan.mapped_slices,
        exported,
        failures,
        composite=composite,
        original_size=scale_plan.is_original_size,
        exact_pixel_compare=(
            scale_plan.is_original_size
            and encoding_plan.exact_pixels_preserved
        ),
        expected_format=(
            "PNG" if encoding_plan.output_format == "png" else "JPEG"
        ),
        expected_icc_profile=encoding_plan.output_icc_profile,
        check_icc_profile=True,
        expected_alpha=encoding_plan.expected_alpha,
    )
    validation_report = preflight_report.merged(post_export_report)
    if options.write_validation_reports:
        try:
            validation_json_path, validation_text_path = (
                validation_report.write(output_directory)
            )
        except Exception as error:
            failures.append(
                ExportFailure(
                    message=f"Validation report could not be written: {error}",
                    exception_type=type(error).__name__,
                )
            )

    status: ExportStatus
    if cancelled:
        status = "cancelled"
    elif failures or not validation_report.passed:
        status = "completed_with_errors"
    else:
        status = "completed"

    if options.create_zip and status == "completed":
        _emit(
            progress_callback,
            phase="archiving",
            current=total,
            total=total,
        )
        try:
            archive_path = Path(
                shutil.make_archive(
                    str(output_directory),
                    "zip",
                    root_dir=output_directory,
                )
            )
        except Exception as error:
            failures.append(
                ExportFailure(
                    message=f"ZIP creation failed: {error}",
                    exception_type=type(error).__name__,
                )
            )
            status = "completed_with_errors"

    source_unchanged = (
        source_signature_before is not None
        and _source_signature(source_path) == source_signature_before
    )
    return ExportResult(
        source_path=source_path,
        output_directory=output_directory,
        archive_path=archive_path,
        status=status,
        exported_slices=tuple(exported),
        failures=tuple(failures),
        slice_issues=slice_result.issues,
        composite_warning=composite.warning,
        source_unchanged=source_unchanged,
        elapsed_seconds=time.perf_counter() - started,
        output_format=encoding_plan.output_format,
        color_policy=encoding_plan.color_policy,
        target_width=scale_plan.output_width,
        scale=scale_plan.scale,
        resize_strategy=resize_strategy,
        validation_report=validation_report,
        validation_json_path=validation_json_path,
        validation_text_path=validation_text_path,
    )


def export_prepared_original_size(
    source_path: Path,
    slice_result: SliceParseResult,
    composite: CompositeResult,
    options: ExportOptions,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> ExportResult:
    """Compatibility wrapper that always exports original dimensions."""

    return export_prepared_slices(
        source_path,
        slice_result,
        composite,
        replace(options, target_width=None),
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )


def export_slices(
    source_path: str | Path,
    options: ExportOptions | None = None,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> ExportResult:
    """Open a PSD/PSB and export slices at original or target width."""

    source = Path(source_path)
    if not source.is_file():
        raise ExportPreflightError(f"Source file does not exist: {source}")
    try:
        psd = PSDImage.open(source)
        slice_result = parse_document_slices(psd)
        composite = read_embedded_composite(psd)
    except ExportServiceError:
        raise
    except Exception as error:
        raise ExportPreflightError(
            f"Unable to prepare '{source.name}' for export: {error}"
        ) from error
    finally:
        if "psd" in locals():
            del psd

    if composite.image is None:
        raise ExportPreflightError(
            composite.error or "No embedded composite is available for export."
        )
    try:
        return export_prepared_slices(
            source,
            slice_result,
            composite,
            options or ExportOptions(),
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
    finally:
        composite.image.close()


def export_original_size(
    source_path: str | Path,
    options: ExportOptions | None = None,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> ExportResult:
    """Compatibility wrapper that always exports original dimensions."""

    original_options = replace(
        options or ExportOptions(),
        target_width=None,
    )
    return export_slices(
        source_path,
        original_options,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )
