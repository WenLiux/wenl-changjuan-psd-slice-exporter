from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from pathlib import Path

from PIL import Image
from psd_tools import PSDImage

from app.core.composite_reader import read_embedded_composite
from app.core.slice_parser import parse_document_slices
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


def _verify_png(path: Path, expected_size: tuple[int, int]) -> tuple[str, int]:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        if image.size != expected_size:
            raise ValueError(
                f"Saved image size is {image.width} x {image.height}; "
                f"expected {expected_size[0]} x {expected_size[1]}."
            )
        mode = image.mode
    return mode, path.stat().st_size


def export_prepared_original_size(
    source_path: Path,
    slice_result: SliceParseResult,
    composite: CompositeResult,
    options: ExportOptions,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> ExportResult:
    """Export normalized slices from an already decoded merged image."""

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

    source_path = Path(source_path)
    output_parent = options.output_parent or source_path.parent
    output_directory = create_collision_safe_directory(
        output_parent,
        f"{source_path.stem}_{options.folder_label}",
        reserve_zip_path=options.create_zip,
    )
    source_signature_before = _source_signature(source_path)
    started = time.perf_counter()
    exported: list[ExportedSlice] = []
    failures: list[ExportFailure] = []
    archive_path: Path | None = None
    cancelled = False
    total = len(slices)

    _emit(
        progress_callback,
        phase="starting",
        current=0,
        total=total,
    )

    for position, slice_info in enumerate(slices, start=1):
        if cancel_check is not None and cancel_check():
            cancelled = True
            break

        output_path = output_directory / (
            f"slice_{position:02d}_{slice_info.width}x"
            f"{slice_info.height}.png"
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
        try:
            crop = composite.image.crop(slice_info.bounds)
            save_options: dict[str, object] = {
                "format": "PNG",
                "compress_level": options.png_compress_level,
            }
            if composite.icc_profile:
                save_options["icc_profile"] = composite.icc_profile
            crop.save(temporary_path, **save_options)
            temporary_path.replace(output_path)
            mode, file_size = _verify_png(
                output_path,
                (slice_info.width, slice_info.height),
            )
            exported.append(
                ExportedSlice(
                    slice_info=slice_info,
                    output_path=output_path,
                    width=slice_info.width,
                    height=slice_info.height,
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
            if crop is not None:
                crop.close()

    status: ExportStatus
    if cancelled:
        status = "cancelled"
    elif failures:
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
    )


def export_original_size(
    source_path: str | Path,
    options: ExportOptions | None = None,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> ExportResult:
    """Open a PSD/PSB and export its user slices at original dimensions."""

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
        return export_prepared_original_size(
            source,
            slice_result,
            composite,
            options or ExportOptions(),
            progress_callback=progress_callback,
            cancel_check=cancel_check,
        )
    finally:
        composite.image.close()
