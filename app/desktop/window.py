from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from app import __version__
from app.bridge.api import AppApi
from app.config.brand import (
    APP_DIRECTORY,
    APP_VENDOR_DIRECTORY,
    WINDOW_TITLE,
)


def frontend_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS")) / "frontend"
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


def dropped_file_paths(event: Mapping[str, object]) -> tuple[Path, ...]:
    """Extract absolute paths added by pywebview to a native drop event."""

    data_transfer = event.get("dataTransfer")
    if not isinstance(data_transfer, Mapping):
        return ()
    files = data_transfer.get("files")
    if (
        not isinstance(files, Sequence)
        or isinstance(files, (str, bytes, bytearray))
    ):
        return ()

    paths: list[Path] = []
    for item in files:
        if not isinstance(item, Mapping):
            continue
        raw_path = item.get("pywebviewFullPath")
        if isinstance(raw_path, str) and raw_path.strip():
            paths.append(Path(raw_path.strip()))
    return tuple(paths)


def run_webview(*, debug: bool = False) -> int:
    try:
        import webview
    except ImportError as error:
        raise RuntimeError(
            "Web UI 运行组件缺失，请重新安装应用或运行 pip install pywebview。"
        ) from error

    index_path = frontend_directory() / "index.html"
    if not index_path.is_file():
        raise RuntimeError(
            f"Web UI 资源不存在：{index_path}。请先运行前端构建。"
        )

    api = AppApi()
    window = webview.create_window(
        f"{WINDOW_TITLE} · v{__version__}",
        url=index_path.as_uri(),
        js_api=api,
        width=1240,
        height=820,
        min_size=(1100, 720),
        background_color="#080d18",
        confirm_close=False,
    )
    api.attach_window(window)

    def handle_drop(event: dict[str, object]) -> None:
        paths = dropped_file_paths(event)
        if not paths:
            api.publish_bridge_error(
                {
                    "code": "DROP_PATH_UNAVAILABLE",
                    "message": "无法读取拖入文件的完整路径，请重新拖入或使用“选择文件”。",
                    "details": "",
                }
            )
            return
        response = api.load_document(str(paths[0]))
        if not response["success"]:
            api.publish_bridge_error(response["error"])

    drop_handler_installed = False

    def install_drop_handler() -> None:
        nonlocal drop_handler_installed
        if drop_handler_installed:
            return
        from webview.dom import DOMEventHandler

        def allow_file_drop(event: dict[str, object]) -> None:
            del event

        document_events = window.dom.document.events
        document_events.dragenter += DOMEventHandler(
            allow_file_drop,
            prevent_default=True,
        )
        document_events.dragover += DOMEventHandler(
            allow_file_drop,
            prevent_default=True,
            debounce=120,
        )
        document_events.drop += DOMEventHandler(
            handle_drop,
            prevent_default=True,
        )
        drop_handler_installed = True

    window.events.loaded += install_drop_handler
    window.events.closed += api.close
    storage_path = (
        Path(os.getenv("LOCALAPPDATA", str(Path.home())))
        / APP_VENDOR_DIRECTORY
        / APP_DIRECTORY
        / "WebView2"
    )
    storage_path.mkdir(parents=True, exist_ok=True)
    webview.start(
        debug=debug,
        private_mode=False,
        storage_path=str(storage_path),
    )
    api.close()
    return 0
