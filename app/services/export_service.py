from __future__ import annotations

import time
import zipfile
from dataclasses import replace
from pathlib import Path

from PIL import Image

from app.core.image_encoder import (
    ImageEncodingError,
    build_image_encoding_plan,
    prepare_image_for_encoding,
    save_options_for_plan,
)
from app.core.photoshop_bridge import PhotoshopAutomation
from app.core.resizer import (
    ResizePlanError,
    build_scale_plan,
    resize_full_composite,
    resize_mapped_slice,
)
from app.core.validator import (
    validate_export_outputs,
    validate_full_canvas_output,
    validate_slice_layout,
)
from app.models.composite_result import CompositeResult
from app.models.export_result import (
    ExportedSlice,
    ExportFailure,
    ExportOptions,
    ExportResult,
    ExportStatus,
)
from app.models.scale_plan import MappedSlice, ResizeStrategy
from app.models.slice_info import SliceInfo, SliceParseResult
from app.services.document_service import prepare_document
from app.services.errors import (
    ExportCancelledError,
    ExportPreflightError,
)
from app.services.progress import (
    CancelCheck,
    ProgressCallback,
    emit_progress as _emit,
    is_cancelled as _is_cancelled,
    raise_if_cancelled as _raise_if_cancelled,
)
from app.utils.filenames import safe_filename_component
from app.utils.paths import create_collision_safe_directory


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


def _create_zip_archive(
    output_directory: Path,
    *,
    cancel_check: CancelCheck | None,
    progress_callback: ProgressCallback | None,
) -> tuple[Path | None, bool]:
    archive_path = output_directory.with_suffix(".zip")
    temporary_path = archive_path.with_name(f".{archive_path.name}.part")
    files = sorted(
        path for path in output_directory.rglob("*") if path.is_file()
    )
    try:
        with zipfile.ZipFile(
            temporary_path,
            mode="x",
            compression=zipfile.ZIP_DEFLATED,
        ) as archive:
            for position, path in enumerate(files, start=1):
                if _is_cancelled(cancel_check):
                    return None, True
                _emit(
                    progress_callback,
                    phase="archiving",
                    current=position,
                    total=len(files),
                    output_path=path,
                )
                archive.write(path, path.relative_to(output_directory))
        temporary_path.replace(archive_path)
        return archive_path, False
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _output_filename(
    mapped_slice: MappedSlice,
    *,
    position: int,
    extension: str,
    naming_rule: str,
    used_names: set[str],
) -> str:
    dimensions = f"{mapped_slice.width}x{mapped_slice.height}"
    if naming_rule == "legacy_sequence_dimensions":
        stem = f"slice_{position:02d}_{dimensions}"
    elif naming_rule == "sequence_dimensions":
        stem = f"{position:02d}_{dimensions}"
    else:
        name = safe_filename_component(
            mapped_slice.slice_info.name,
            fallback=f"slice_{position:02d}",
        )
        if naming_rule == "slice_name_with_index":
            stem = f"{position:02d}_{name}_{dimensions}"
        else:
            stem = f"{name}_{dimensions}"

    candidate = f"{stem}{extension}"
    duplicate_index = 2
    while candidate.casefold() in used_names:
        candidate = f"{stem}_{duplicate_index:02d}{extension}"
        duplicate_index += 1
    used_names.add(candidate.casefold())
    return candidate


def _full_canvas_filename(
    source_path: Path,
    *,
    width: int,
    height: int,
    extension: str,
) -> str:
    stem = safe_filename_component(
        source_path.stem,
        fallback="document",
    )
    return f"{stem}_full_{width}x{height}{extension}"


def export_prepared_full_canvas(
    source_path: Path,
    slice_result: SliceParseResult,
    composite: CompositeResult,
    options: ExportOptions,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> ExportResult:
    """Export the complete composite as one long image."""

    del slice_result
    _raise_if_cancelled(cancel_check)
    if composite.image is None:
        raise ExportPreflightError(
            composite.error or "No embedded composite is available for export."
        )
    if not composite.is_reliable and not options.allow_unverified_composite:
        raise ExportPreflightError(
            composite.warning
            or "The embedded composite cannot be confirmed as complete."
        )

    try:
        encoding_plan = build_image_encoding_plan(composite, options)
    except ImageEncodingError as error:
        raise ExportPreflightError(str(error)) from error
    try:
        scale_plan = build_scale_plan(
            canvas_width=composite.width,
            canvas_height=composite.height,
            slices=(),
            target_width=options.target_width,
            allow_upscale=options.allow_upscale,
        )
    except ResizePlanError as error:
        raise ExportPreflightError(str(error)) from error

    if (
        not scale_plan.is_original_size
        and scale_plan.estimated_rgba_bytes > options.max_full_resize_bytes
    ):
        estimated_mib = (
            scale_plan.estimated_rgba_bytes / (1024 * 1024)
        )
        limit_mib = options.max_full_resize_bytes / (1024 * 1024)
        raise ExportPreflightError(
            "Complete-canvas export needs one resized image in memory "
            f"(about {estimated_mib:.1f} MiB), above the configured "
            f"{limit_mib:.1f} MiB safety limit. Reduce the target width or "
            "use slice export instead."
        )

    source_path = Path(source_path)
    output_parent = options.output_parent or source_path.parent
    folder_label = options.folder_label
    if folder_label is None:
        folder_label = (
            "full_original"
            if scale_plan.is_original_size
            else f"full_{scale_plan.output_width}px"
        )
    source_signature_before = _source_signature(source_path)
    started = time.perf_counter()
    output_directory: Path
    try:
        output_directory = create_collision_safe_directory(
            output_parent,
            f"{source_path.stem}_{folder_label}",
            reserve_zip_path=options.create_zip,
        )
    except Exception as error:
        raise ExportPreflightError(
            f"Unable to create the output directory: {error}"
        ) from error

    output_path = output_directory / _full_canvas_filename(
        source_path,
        width=scale_plan.output_width,
        height=scale_plan.output_height,
        extension=encoding_plan.extension,
    )
    temporary_path = output_path.with_name(
        f".{output_path.name}.part"
    )
    failures: list[ExportFailure] = []
    archive_path: Path | None = None
    validation_json_path: Path | None = None
    validation_text_path: Path | None = None
    cancelled = False
    render_image: Image.Image | None = composite.image
    resized_composite: Image.Image | None = None
    if not scale_plan.is_original_size:
        _emit(
            progress_callback,
            phase="resizing",
            current=0,
            total=1,
        )
        _raise_if_cancelled(cancel_check)
        try:
            resized_composite = resize_full_composite(
                composite.image,
                scale_plan,
            )
        except Exception as error:
            raise ExportPreflightError(
                f"Unable to resize the complete composite: {error}"
            ) from error
        if _is_cancelled(cancel_check):
            resized_composite.close()
            raise ExportCancelledError("Export was cancelled after resizing.")
        render_image = resized_composite

    _emit(
        progress_callback,
        phase="starting",
        current=0,
        total=1,
    )
    try:
        if _is_cancelled(cancel_check):
            cancelled = True
        else:
            _emit(
                progress_callback,
                phase="exporting",
                current=1,
                total=1,
                output_path=output_path,
            )
            encoded_image: Image.Image | None = None
            try:
                if render_image is None:
                    raise RuntimeError("Complete render image is unavailable.")
                encoded_image = prepare_image_for_encoding(
                    render_image,
                    encoding_plan,
                )
                save_options = save_options_for_plan(encoding_plan)
                if encoding_plan.output_format == "png":
                    save_options["compress_level"] = (
                        options.png_compress_level
                    )
                encoded_image.save(temporary_path, **save_options)
                temporary_path.replace(output_path)
                _verify_image(
                    output_path,
                    (
                        scale_plan.output_width,
                        scale_plan.output_height,
                    ),
                    (
                        "PNG"
                        if encoding_plan.output_format == "png"
                        else "JPEG"
                    ),
                )
                _emit(
                    progress_callback,
                    phase="written",
                    current=1,
                    total=1,
                    output_path=output_path,
                )
            except Exception as error:
                if temporary_path.exists():
                    temporary_path.unlink()
                failures.append(
                    ExportFailure(
                        message=f"Complete long image could not be exported: {error}",
                        output_path=output_path,
                        exception_type=type(error).__name__,
                    )
                )
            finally:
                if encoded_image is not None:
                    encoded_image.close()
    finally:
        if resized_composite is not None:
            resized_composite.close()

    _emit(
        progress_callback,
        phase="validating",
        current=1 if output_path.is_file() else 0,
        total=1,
    )
    post_export_report = validate_full_canvas_output(
        output_path,
        composite=composite,
        expected_size=(
            scale_plan.output_width,
            scale_plan.output_height,
        ),
        expected_format=(
            "PNG" if encoding_plan.output_format == "png" else "JPEG"
        ),
        expected_icc_profile=encoding_plan.output_icc_profile,
        expected_alpha=encoding_plan.expected_alpha,
        exact_pixel_compare=(
            scale_plan.is_original_size
            and encoding_plan.exact_pixels_preserved
        ),
        cancel_check=cancel_check,
    )
    validation_report = post_export_report
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
    if status == "completed" and _is_cancelled(cancel_check):
        status = "cancelled"

    if options.create_zip and status == "completed":
        _emit(
            progress_callback,
            phase="archiving",
            current=1,
            total=1,
        )
        try:
            archive_path, archive_cancelled = _create_zip_archive(
                output_directory,
                cancel_check=cancel_check,
                progress_callback=progress_callback,
            )
            if archive_cancelled:
                status = "cancelled"
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
        exported_slices=(),
        failures=tuple(failures),
        slice_issues=(),
        composite_source=composite.source,
        composite_warning=composite.warning,
        source_unchanged=source_unchanged,
        elapsed_seconds=time.perf_counter() - started,
        output_format=encoding_plan.output_format,
        color_policy=encoding_plan.color_policy,
        target_width=scale_plan.output_width,
        scale=scale_plan.scale,
        resize_strategy=(
            "none" if scale_plan.is_original_size else "full_canvas"
        ),
        validation_report=validation_report,
        validation_json_path=validation_json_path,
        validation_text_path=validation_text_path,
        export_mode="full_canvas",
        output_path=output_path if output_path.is_file() else None,
    )


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

    if options.export_mode == "full_canvas":
        return export_prepared_full_canvas(
            source_path,
            slice_result,
            composite,
            options,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
    _raise_if_cancelled(cancel_check)
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
    used_output_names: set[str] = set()
    resized_composite: Image.Image | None = None
    render_image: Image.Image | None
    resize_strategy: ResizeStrategy
    if scale_plan.is_original_size:
        render_image = composite.image
        resize_strategy = "none"
    elif scale_plan.estimated_rgba_bytes <= options.max_full_resize_bytes:
        _emit(
            progress_callback,
            phase="resizing",
            current=0,
            total=total,
        )
        _raise_if_cancelled(cancel_check)
        try:
            resized_composite = resize_full_composite(
                composite.image,
                scale_plan,
            )
        except Exception as error:
            raise ExportPreflightError(
                f"Unable to resize the complete composite: {error}"
            ) from error
        if _is_cancelled(cancel_check):
            resized_composite.close()
            raise ExportCancelledError("Export was cancelled after resizing.")
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
            if _is_cancelled(cancel_check):
                cancelled = True
                break

            output_path = output_directory / _output_filename(
                mapped_slice,
                position=position,
                extension=encoding_plan.extension,
                naming_rule=options.naming_rule,
                used_names=used_output_names,
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

    _emit(
        progress_callback,
        phase="validating",
        current=len(exported),
        total=total,
    )
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
        cancel_check=cancel_check,
        progress_callback=lambda current, validation_total: _emit(
            progress_callback,
            phase="validating",
            current=current,
            total=validation_total,
        ),
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

    if status == "completed" and _is_cancelled(cancel_check):
        status = "cancelled"

    if options.create_zip and status == "completed":
        _emit(
            progress_callback,
            phase="archiving",
            current=total,
            total=total,
        )
        try:
            archive_path, archive_cancelled = _create_zip_archive(
                output_directory,
                cancel_check=cancel_check,
                progress_callback=progress_callback,
            )
            if archive_cancelled:
                status = "cancelled"
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
        composite_source=composite.source,
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
    photoshop_automation: PhotoshopAutomation | None = None,
) -> ExportResult:
    """Open a PSD/PSB and export slices at original or target width."""

    effective_options = options or ExportOptions()
    with prepare_document(
        source_path,
        effective_options,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
        photoshop_automation=photoshop_automation,
    ) as prepared:
        return export_prepared_slices(
            prepared.source_path,
            prepared.slice_result,
            prepared.composite,
            effective_options,
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )


def export_original_size(
    source_path: str | Path,
    options: ExportOptions | None = None,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    photoshop_automation: PhotoshopAutomation | None = None,
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
        photoshop_automation=photoshop_automation,
    )


def export_full_canvas(
    source_path: str | Path,
    options: ExportOptions | None = None,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    photoshop_automation: PhotoshopAutomation | None = None,
) -> ExportResult:
    """Export one complete canvas image instead of individual slices."""

    full_options = replace(
        options or ExportOptions(),
        export_mode="full_canvas",
    )
    return export_slices(
        source_path,
        full_options,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
        photoshop_automation=photoshop_automation,
    )
