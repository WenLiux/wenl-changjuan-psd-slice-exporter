from __future__ import annotations

from io import BytesIO
from pathlib import Path

from psd_tools import PSDImage

from app.core.composite_reader import read_embedded_composite
from app.core.photoshop_bridge import (
    PhotoshopAutomation,
    PhotoshopBridgeError,
    PhotoshopCompositeOptions,
    read_photoshop_composite,
)
from app.core.slice_parser import (
    SliceResourceMissingError,
    parse_document_slices,
)
from app.models.composite_result import CompositeResult
from app.models.export_result import ExportOptions, ExportResult
from app.models.prepared_document import (
    DocumentLoadResult,
    PreparedDocument,
    SourceFingerprint,
)
from app.models.slice_info import SliceIssue, SliceParseResult
from app.services.errors import (
    ExportPreflightError,
    ExportServiceError,
)
from app.services.progress import (
    CancelCheck,
    ProgressCallback,
    emit_progress,
    raise_if_cancelled,
)


def _fingerprint(path: Path) -> SourceFingerprint:
    try:
        return SourceFingerprint.read(path)
    except Exception as error:
        raise ExportPreflightError(
            f"Unable to fingerprint '{path.name}': {error}"
        ) from error


def _close_composite(composite: CompositeResult | None) -> None:
    if composite is not None and composite.image is not None:
        composite.image.close()


def prepare_document(
    source_path: str | Path,
    options: ExportOptions | None = None,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
    photoshop_automation: PhotoshopAutomation | None = None,
    allow_unavailable: bool = False,
) -> PreparedDocument:
    """Parse and cache one document for repeated desktop exports."""

    effective_options = options or ExportOptions()
    source = Path(source_path)
    if not source.is_file():
        raise ExportPreflightError(f"Source file does not exist: {source}")
    if source.suffix.lower() not in {".psd", ".psb"}:
        raise ExportPreflightError(
            "Only Photoshop PSD and PSB files are supported."
        )

    emit_progress(
        progress_callback,
        phase="preparing",
        current=0,
        total=0,
    )
    raise_if_cancelled(cancel_check)
    fingerprint_before = _fingerprint(source)
    composite: CompositeResult | None = None
    try:
        emit_progress(
            progress_callback,
            phase="parsing",
            current=0,
            total=0,
        )
        psd = PSDImage.open(source)
        try:
            slice_result = parse_document_slices(psd)
        except SliceResourceMissingError:
            slice_result = SliceParseResult(
                source_version="none",
                all_slices=(),
                exportable_slices=(),
                excluded_slices=(),
                issues=(
                    SliceIssue(
                        code="no_slice_resource",
                        message=(
                            "The document has no Photoshop slice resource; "
                            "complete-canvas export remains available."
                        ),
                    ),
                ),
            )
        raise_if_cancelled(cancel_check)
        emit_progress(
            progress_callback,
            phase="reading_composite",
            current=0,
            total=len(slice_result.exportable_slices),
        )
        composite = read_embedded_composite(psd)
        raise_if_cancelled(
            cancel_check,
            close_image=composite.image,
        )
    except ExportServiceError:
        raise
    except Exception as error:
        raise ExportPreflightError(
            f"Unable to prepare '{source.name}' for export: {error}"
        ) from error
    finally:
        if "psd" in locals():
            del psd

    use_photoshop = (
        effective_options.photoshop_fallback == "always"
        or (
            effective_options.photoshop_fallback == "if_needed"
            and not composite.is_reliable
        )
    )
    if use_photoshop:
        emit_progress(
            progress_callback,
            phase="photoshop",
            current=0,
            total=len(slice_result.exportable_slices),
        )
        raise_if_cancelled(cancel_check)
        if effective_options.photoshop_fallback == "always":
            fallback_reason = "Photoshop rendering was explicitly requested."
        else:
            fallback_reason = (
                composite.error
                or composite.warning
                or "The embedded composite could not be verified."
            )
        source_color_mode = composite.color_mode
        source_depth = composite.depth
        source_icc_profile = composite.icc_profile
        expected_has_alpha = composite.has_alpha
        expected_width = composite.width
        expected_height = composite.height
        _close_composite(composite)
        composite = None
        try:
            composite = read_photoshop_composite(
                source,
                expected_width=expected_width,
                expected_height=expected_height,
                source_color_mode=source_color_mode,
                source_depth=source_depth,
                source_icc_profile=source_icc_profile,
                expected_has_alpha=expected_has_alpha,
                options=PhotoshopCompositeOptions(
                    allow_launch=effective_options.photoshop_allow_launch,
                    png_compression=effective_options.png_compress_level,
                ),
                automation=photoshop_automation,
            )
        except PhotoshopBridgeError as error:
            raise ExportPreflightError(
                f"Photoshop high-fidelity fallback failed: {error}"
            ) from error
        composite.warning = (
            "Photoshop high-fidelity fallback was used. Reason: "
            f"{fallback_reason}"
        )
        raise_if_cancelled(
            cancel_check,
            close_image=composite.image,
        )

    if composite.image is None and not allow_unavailable:
        raise ExportPreflightError(
            composite.error or "No embedded composite is available for export."
        )

    try:
        fingerprint_after = _fingerprint(source)
    except Exception:
        _close_composite(composite)
        raise
    if fingerprint_after != fingerprint_before:
        _close_composite(composite)
        raise ExportPreflightError(
            "The PSD/PSB changed while it was being loaded. Reload the file "
            "and try again."
        )
    return PreparedDocument(
        source_path=source,
        fingerprint=fingerprint_after,
        slice_result=slice_result,
        composite=composite,
        preparation_mode=effective_options.photoshop_fallback,
    )


def _preparation_is_compatible(
    prepared: PreparedDocument,
    options: ExportOptions,
) -> bool:
    if prepared.preparation_mode == options.photoshop_fallback:
        return True
    return (
        prepared.composite.source == "embedded_merged"
        and prepared.composite.is_reliable
        and prepared.preparation_mode in {"disabled", "if_needed"}
        and options.photoshop_fallback in {"disabled", "if_needed"}
    )


def export_prepared_document(
    prepared: PreparedDocument,
    options: ExportOptions,
    *,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> ExportResult:
    """Export a cached document without reparsing its PSD/PSB data."""

    if not _preparation_is_compatible(prepared, options):
        raise ExportPreflightError(
            "The Photoshop fallback setting changed after the document was "
            "loaded. Reload the file before exporting."
        )
    try:
        prepared.ensure_current()
    except Exception as error:
        raise ExportPreflightError(str(error)) from error
    raise_if_cancelled(cancel_check)

    # Local import avoids a module cycle: the convenience export_slices()
    # function imports prepare_document from this module.
    from app.services.export_service import export_prepared_slices

    return export_prepared_slices(
        prepared.source_path,
        prepared.slice_result,
        prepared.composite,
        options,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )


def build_document_load_result(
    prepared: PreparedDocument,
    *,
    preview_size: tuple[int, int] = (520, 280),
) -> DocumentLoadResult:
    """Build a small immutable payload without exposing the cached PIL image."""

    preview_png: bytes | None = None
    preview_slice_index: int | None = None
    image = prepared.composite.image
    slices = prepared.slice_result.exportable_slices
    if image is not None:
        if slices:
            first_slice = slices[0]
            preview_slice_index = first_slice.index
            crop = image.crop(first_slice.bounds)
        else:
            crop = image.copy()
        try:
            crop.thumbnail(preview_size)
            buffer = BytesIO()
            crop.save(buffer, format="PNG", compress_level=3)
            preview_png = buffer.getvalue()
        finally:
            crop.close()
    return DocumentLoadResult(
        summary=prepared.summary,
        preview_png=preview_png,
        preview_slice_index=preview_slice_index,
    )
