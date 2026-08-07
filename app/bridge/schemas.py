from __future__ import annotations

from dataclasses import asdict
from typing import Any

from app.models.app_settings import AppSettings
from app.models.export_result import ExportProgress, ExportResult
from app.models.prepared_document import DocumentLoadResult, DocumentSummary
from app.models.slice_info import SliceInfo


def ok(data: Any = None) -> dict[str, Any]:
    return {"success": True, "data": data, "error": None}


def failure(code: str, message: str, details: str = "") -> dict[str, Any]:
    return {
        "success": False,
        "data": None,
        "error": {"code": code, "message": message, "details": details},
    }


def settings_payload(settings: AppSettings) -> dict[str, Any]:
    payload = asdict(settings)
    payload["output_directory"] = (
        str(settings.output_directory)
        if settings.output_directory is not None
        else ""
    )
    return payload


def slice_payload(item: SliceInfo) -> dict[str, Any]:
    return {
        "id": f"slice-{item.slice_id if item.slice_id is not None else item.index}",
        "index": item.index,
        "slice_id": item.slice_id,
        "name": item.name or "未命名",
        "left": item.left,
        "top": item.top,
        "right": item.right,
        "bottom": item.bottom,
        "width": item.width,
        "height": item.height,
        "is_automatic": item.is_automatic,
    }


def summary_payload(summary: DocumentSummary) -> dict[str, Any]:
    return {
        "source_path": str(summary.source_path),
        "file_name": summary.source_path.name,
        "source_size": summary.source_size,
        "width": summary.width,
        "height": summary.height,
        "color_mode": summary.color_mode,
        "depth": summary.depth,
        "has_alpha": summary.has_alpha,
        "source_version": summary.source_version,
        "slice_count": summary.slice_count,
        "excluded_slice_count": summary.excluded_slice_count,
        "slices": [slice_payload(item) for item in summary.slices],
        "issues": [
            {
                "code": issue.code,
                "message": issue.message,
                "severity": issue.severity,
                "slice_index": issue.slice_index,
            }
            for issue in summary.issues
        ],
        "composite_source": summary.composite_source,
        "composite_is_available": summary.composite_is_available,
        "composite_is_reliable": summary.composite_is_reliable,
        "composite_warning": summary.composite_warning,
        "composite_error": summary.composite_error,
        "preparation_mode": summary.preparation_mode,
    }


def document_payload(
    result: DocumentLoadResult,
    *,
    preview_url: str | None,
) -> dict[str, Any]:
    payload = summary_payload(result.summary)
    payload["preview_url"] = preview_url
    payload["preview_slice_index"] = result.preview_slice_index
    return payload


def progress_payload(progress: ExportProgress) -> dict[str, Any]:
    return {
        "phase": progress.phase,
        "current": progress.current,
        "total": progress.total,
        "slice": (
            slice_payload(progress.slice_info)
            if progress.slice_info is not None
            else None
        ),
        "output_path": (
            str(progress.output_path)
            if progress.output_path is not None
            else None
        ),
    }


def export_result_payload(result: ExportResult) -> dict[str, Any]:
    exported_count = (
        len(result.exported_slices)
        if result.export_mode == "slices"
        else int(result.output_path is not None)
    )
    return {
        "status": result.status,
        "success": result.success,
        "export_mode": result.export_mode,
        "source_path": str(result.source_path),
        "output_directory": str(result.output_directory),
        "output_path": (
            str(result.output_path) if result.output_path is not None else None
        ),
        "archive_path": (
            str(result.archive_path) if result.archive_path is not None else None
        ),
        "exported_count": exported_count,
        "failure_count": len(result.failures),
        "failures": [item.message for item in result.failures],
        "elapsed_seconds": result.elapsed_seconds,
        "output_format": result.output_format,
        "target_width": result.target_width,
        "validation_passed": result.validation_report.passed,
        "validation_text_path": (
            str(result.validation_text_path)
            if result.validation_text_path is not None
            else None
        ),
        "validation_json_path": (
            str(result.validation_json_path)
            if result.validation_json_path is not None
            else None
        ),
    }
