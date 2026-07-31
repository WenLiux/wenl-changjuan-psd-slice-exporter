from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PIL import Image

from app.models.export_result import ExportProgress, ProgressPhase
from app.models.slice_info import SliceInfo
from app.services.errors import ExportCancelledError


ProgressCallback = Callable[[ExportProgress], None]
CancelCheck = Callable[[], bool]


def emit_progress(
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


def is_cancelled(cancel_check: CancelCheck | None) -> bool:
    return cancel_check is not None and cancel_check()


def raise_if_cancelled(
    cancel_check: CancelCheck | None,
    *,
    close_image: Image.Image | None = None,
) -> None:
    if not is_cancelled(cancel_check):
        return
    if close_image is not None:
        close_image.close()
    raise ExportCancelledError("Export was cancelled.")
