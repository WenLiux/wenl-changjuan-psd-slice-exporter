from __future__ import annotations

import json
import os
import queue
import shutil
import tempfile
import threading
import traceback
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from app import __version__
from app.config.brand import BRAND_NAME, FULL_PRODUCT_NAME, FUNCTIONAL_SLOGAN
from app.bridge.schemas import (
    document_payload,
    export_result_payload,
    failure,
    ok,
    progress_payload,
    settings_payload,
)
from app.models.app_settings import AppSettings
from app.models.export_result import ExportOptions, ExportResult
from app.models.prepared_document import DocumentLoadResult, DocumentSummary
from app.services.document_service import (
    build_document_load_result,
    export_prepared_document,
    prepare_document,
)
from app.services.settings_store import SettingsStore
from app.ui.app_state import FormValidationError, build_export_options
from app.ui.task_runner import (
    Cancelled,
    Failed,
    Progress,
    Started,
    Succeeded,
    TaskEvent,
    TaskRunner,
)


EventSink = Callable[[dict[str, Any]], None]


class AppApi:
    """Small JSON-only API exposed to the pywebview JavaScript bridge."""

    def __init__(self, settings_store: SettingsStore | None = None) -> None:
        self._settings_store = settings_store or SettingsStore()
        load = self._settings_store.load_with_diagnostics()
        self._settings = load.settings
        self._settings_warnings = load.warnings
        self._summary: DocumentSummary | None = None
        self._last_result: ExportResult | None = None
        self._window: Any | None = None
        self._event_sink: EventSink | None = None
        self._event_backlog: queue.Queue[dict[str, Any]] = queue.Queue()
        self._operations: dict[int, str] = {}
        self._pending_export: ExportOptions | None = None
        self._lock = threading.RLock()
        self._closed = threading.Event()
        self._cache_directory = Path(
            tempfile.mkdtemp(prefix="wenl-changjuan-")
        )
        self._runner = TaskRunner(
            load_handler=prepare_document,
            export_handler=export_prepared_document,
            session_result=build_document_load_result,
        )
        self._dispatcher = threading.Thread(
            target=self._dispatch_events,
            name="psd-slice-web-event-dispatcher",
            daemon=True,
        )
        self._dispatcher.start()

    def attach_window(self, window: Any) -> None:
        self._window = window

        def send(payload: dict[str, Any]) -> None:
            serialized = json.dumps(payload, ensure_ascii=False)
            window.evaluate_js(
                f"window.__PSD_SLICE_EVENT__?.({serialized})"
            )

        self._event_sink = send

    def get_initial_state(self) -> dict[str, Any]:
        return self._guard(
            lambda: ok(
                {
                    "version": __version__,
                    "brand": {
                        "name": BRAND_NAME,
                        "full_product_name": FULL_PRODUCT_NAME,
                        "functional_slogan": FUNCTIONAL_SLOGAN,
                    },
                    "settings": settings_payload(self._settings),
                    "settings_warnings": list(self._settings_warnings),
                    "platform": "Windows" if os.name == "nt" else os.name,
                }
            ),
            "INITIAL_STATE_FAILED",
        )

    def get_events(self) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        while len(events) < 100:
            try:
                events.append(self._event_backlog.get_nowait())
            except queue.Empty:
                break
        return ok(events)

    def select_input_file(self) -> dict[str, Any]:
        return self._guard(self._select_input_file, "FILE_DIALOG_FAILED")

    def load_document(
        self,
        path: str,
        options: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._guard(
            lambda: self._load_document(path, options),
            "DOCUMENT_LOAD_FAILED",
        )

    def select_output_directory(self) -> dict[str, Any]:
        return self._guard(
            self._select_output_directory,
            "DIRECTORY_DIALOG_FAILED",
        )

    def save_settings(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._guard(
            lambda: self._save_settings(payload),
            "SETTINGS_SAVE_FAILED",
        )

    def start_export(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._guard(
            lambda: self._start_export(payload),
            "EXPORT_START_FAILED",
        )

    def cancel_export(self, task_id: int | None = None) -> dict[str, Any]:
        del task_id
        return self._guard(
            lambda: ok({"cancelled": self._runner.request_cancel()}),
            "CANCEL_FAILED",
        )

    def open_output_directory(self, path: str | None = None) -> dict[str, Any]:
        return self._guard(
            lambda: self._open_output_directory(path),
            "OPEN_OUTPUT_FAILED",
        )

    def open_report(self, path: str | None = None) -> dict[str, Any]:
        return self._guard(
            lambda: self._open_report(path),
            "OPEN_REPORT_FAILED",
        )

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        self._runner.close()
        shutil.rmtree(self._cache_directory, ignore_errors=True)

    def publish_bridge_error(self, error: object) -> None:
        """Forward native host failures through the normal UI event channel."""

        if isinstance(error, dict):
            payload = error
        else:
            payload = {
                "code": "DESKTOP_BRIDGE_ERROR",
                "message": str(error),
                "details": "",
            }
        self._publish({"type": "bridge_error", "error": payload})

    def _select_input_file(self) -> dict[str, Any]:
        if self._window is None:
            raise RuntimeError("桌面窗口尚未准备好。")
        import webview

        dialog_type = getattr(
            getattr(webview, "FileDialog", object),
            "OPEN",
            getattr(webview, "OPEN_DIALOG", 10),
        )
        selection = self._window.create_file_dialog(
            dialog_type,
            allow_multiple=False,
            file_types=("Photoshop 文件 (*.psd;*.psb)",),
        )
        return ok({"path": self._first_dialog_path(selection)})

    def _select_output_directory(self) -> dict[str, Any]:
        if self._window is None:
            raise RuntimeError("桌面窗口尚未准备好。")
        import webview

        dialog_type = getattr(
            getattr(webview, "FileDialog", object),
            "FOLDER",
            getattr(webview, "FOLDER_DIALOG", 20),
        )
        selection = self._window.create_file_dialog(dialog_type)
        return ok({"path": self._first_dialog_path(selection)})

    @staticmethod
    def _first_dialog_path(selection: Any) -> str:
        if not selection:
            return ""
        if isinstance(selection, (str, Path)):
            return str(selection)
        first = selection[0]
        return str(getattr(first, "path", first))

    def _load_document(
        self,
        path_value: str,
        options: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        path = Path(path_value)
        if not path.is_file() or path.suffix.lower() not in {".psd", ".psb"}:
            return failure(
                "INVALID_SOURCE_FILE",
                "请选择存在的 PSD 或 PSB 文件。",
            )
        if self._runner.is_running:
            return failure("TASK_BUSY", "已有任务正在运行，请稍候。")
        preparation = options or {}
        prepare_options = ExportOptions(
            photoshop_fallback=str(
                preparation.get("photoshop_fallback", "disabled")
            ),
            photoshop_allow_launch=bool(
                preparation.get("photoshop_allow_launch", False)
            ),
            allow_unverified_composite=bool(
                preparation.get("allow_unverified_composite", False)
            ),
        )
        with self._lock:
            self._summary = None
            self._pending_export = None
            task_id = self._runner.start_load(
                path,
                prepare_options,
                allow_unavailable=True,
            )
            self._operations[task_id] = "load"
        return ok({"task_id": task_id, "path": str(path)})

    def _save_settings(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        settings = self._settings_from_payload(payload)
        self._settings_store.save(settings)
        self._settings = settings
        return ok(settings_payload(settings))

    def _start_export(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        if self._summary is None:
            return failure("NO_DOCUMENT", "请先加载 PSD 或 PSB 文件。")
        if self._runner.is_running:
            return failure("TASK_BUSY", "已有任务正在运行，请稍候。")
        settings_value = payload.get("settings", payload)
        if not isinstance(settings_value, Mapping):
            raise FormValidationError("导出设置格式不正确。")
        settings = self._settings_from_payload(settings_value)
        selected_value = payload.get("selected_slice_indices")
        selected = (
            None
            if selected_value is None
            else frozenset(int(value) for value in selected_value)
        )
        options = build_export_options(
            settings,
            self._summary,
            output_directory=settings.output_directory,
            selected_slice_indices=selected,
            photoshop_allow_launch=bool(
                payload.get("photoshop_allow_launch", False)
            ),
            allow_mode_conversion=bool(
                payload.get("allow_mode_conversion", False)
            ),
            allow_unverified_composite=bool(
                payload.get("allow_unverified_composite", False)
            ),
        )
        self._settings_store.save(settings)
        self._settings = settings

        if not self._cache_matches_options(options):
            self._pending_export = options
            task_id = self._runner.start_load(
                self._summary.source_path,
                ExportOptions(
                    photoshop_fallback=options.photoshop_fallback,
                    photoshop_allow_launch=options.photoshop_allow_launch,
                    allow_unverified_composite=options.allow_unverified_composite,
                ),
                allow_unavailable=True,
            )
            self._operations[task_id] = "load_for_export"
            return ok({"task_id": task_id, "reloading": True})

        if not self._summary.composite_is_available:
            return failure(
                "COMPOSITE_UNAVAILABLE",
                self._summary.composite_error
                or "合成图不可用，请启用 Photoshop 高保真回退后重试。",
            )
        task_id = self._runner.start_export(options)
        self._operations[task_id] = "export"
        self._last_result = None
        return ok({"task_id": task_id, "reloading": False})

    def _settings_from_payload(self, payload: Mapping[str, Any]) -> AppSettings:
        output_directory = str(payload.get("output_directory", "")).strip()
        return AppSettings(
            output_directory=(
                Path(output_directory) if output_directory else None
            ),
            export_mode=str(payload.get("export_mode", "slices")),
            width_mode=str(payload.get("width_mode", "original")),
            target_width=int(payload.get("target_width", 1440)),
            allow_upscale=bool(payload.get("allow_upscale", True)),
            output_format=str(payload.get("output_format", "png")),
            jpeg_quality=int(payload.get("jpeg_quality", 95)),
            jpeg_background=str(
                payload.get("jpeg_background", "#FFFFFF")
            ).upper(),
            color_policy=str(payload.get("color_policy", "auto")),
            create_zip=bool(payload.get("create_zip", False)),
            open_output_folder=bool(
                payload.get("open_output_folder", True)
            ),
            naming_rule=str(
                payload.get("naming_rule", "sequence_dimensions")
            ),
            photoshop_fallback=str(
                payload.get("photoshop_fallback", "disabled")
            ),
        )

    def _cache_matches_options(self, options: ExportOptions) -> bool:
        if self._summary is None:
            return False
        prepared_mode = self._summary.preparation_mode
        requested_mode = options.photoshop_fallback
        if prepared_mode == requested_mode:
            return True
        return (
            self._summary.composite_source == "embedded_merged"
            and self._summary.composite_is_reliable
            and prepared_mode in {"disabled", "if_needed"}
            and requested_mode in {"disabled", "if_needed"}
        )

    def _dispatch_events(self) -> None:
        while not self._closed.is_set() or self._runner.worker_alive:
            try:
                event = self._runner.events.get(timeout=0.2)
            except queue.Empty:
                continue
            payload = self._event_payload(event)
            if payload is not None:
                self._publish(payload)

    def _event_payload(self, event: TaskEvent) -> dict[str, Any] | None:
        operation = self._operations.get(event.task_id, "unknown")
        base = {"task_id": event.task_id, "operation": operation}
        if isinstance(event, Started):
            return {**base, "type": "task_started"}
        if isinstance(event, Progress):
            return {
                **base,
                "type": "task_progress",
                "progress": progress_payload(event.value),
            }
        if isinstance(event, Failed):
            self._operations.pop(event.task_id, None)
            self._pending_export = None
            return {
                **base,
                "type": "task_failed",
                "error": {
                    "code": "TASK_FAILED",
                    "message": event.message or "任务失败。",
                    "details": event.traceback_text,
                },
            }
        if isinstance(event, Cancelled):
            self._operations.pop(event.task_id, None)
            self._pending_export = None
            result = (
                export_result_payload(event.result)
                if isinstance(event.result, ExportResult)
                else None
            )
            if isinstance(event.result, ExportResult):
                self._last_result = event.result
            return {
                **base,
                "type": "task_cancelled",
                "message": event.message or "任务已取消。",
                "result": result,
            }
        if not isinstance(event, Succeeded):
            return None

        self._operations.pop(event.task_id, None)
        if isinstance(event.result, DocumentLoadResult):
            self._summary = event.result.summary
            payload = {
                **base,
                "type": "document_loaded",
                "document": document_payload(
                    event.result,
                    preview_url=self._write_preview(event.result.preview_png),
                ),
            }
            pending = self._pending_export
            self._pending_export = None
            if operation == "load_for_export" and pending is not None:
                if not event.result.summary.composite_is_available:
                    payload["follow_up_error"] = (
                        event.result.summary.composite_error
                        or "合成图不可用，无法继续导出。"
                    )
                else:
                    task_id = self._runner.start_export(pending)
                    self._operations[task_id] = "export"
                    payload["follow_up_task_id"] = task_id
            return payload
        if isinstance(event.result, ExportResult):
            self._last_result = event.result
            if event.result.success and self._settings.open_output_folder:
                try:
                    self._open_path(event.result.output_directory)
                except OSError:
                    pass
            return {
                **base,
                "type": "export_completed",
                "result": export_result_payload(event.result),
            }
        return {**base, "type": "task_completed", "result": None}

    def _write_preview(self, png_bytes: bytes | None) -> str | None:
        if png_bytes is None:
            return None
        path = self._cache_directory / "document-preview.png"
        path.write_bytes(png_bytes)
        return f"{path.as_uri()}?v={path.stat().st_mtime_ns}"

    def _publish(self, payload: dict[str, Any]) -> None:
        sink = self._event_sink
        if sink is not None:
            try:
                sink(payload)
                return
            except Exception:
                pass
        self._event_backlog.put(payload)

    def _open_output_directory(self, path: str | None) -> dict[str, Any]:
        target = (
            Path(path)
            if path
            else (
                self._last_result.output_directory
                if self._last_result is not None
                else None
            )
        )
        if target is None or not target.exists():
            return failure("OUTPUT_NOT_FOUND", "尚无可打开的输出目录。")
        self._open_path(target if target.is_dir() else target.parent)
        return ok({"path": str(target)})

    def _open_report(self, path: str | None) -> dict[str, Any]:
        target = (
            Path(path)
            if path
            else (
                self._last_result.validation_text_path
                if self._last_result is not None
                else None
            )
        )
        if target is None or not target.is_file():
            return failure("REPORT_NOT_FOUND", "尚无可查看的验证报告。")
        self._open_path(target)
        return ok({"path": str(target)})

    @staticmethod
    def _open_path(path: Path) -> None:
        if os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
            return
        import subprocess

        subprocess.Popen(["xdg-open", str(path)])

    @staticmethod
    def _guard(
        callback: Callable[[], dict[str, Any]],
        code: str,
    ) -> dict[str, Any]:
        try:
            return callback()
        except (FormValidationError, TypeError, ValueError) as error:
            return failure("VALIDATION_ERROR", str(error))
        except Exception as error:
            return failure(code, str(error), traceback.format_exc())
