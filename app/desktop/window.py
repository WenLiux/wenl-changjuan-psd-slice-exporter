from __future__ import annotations

import os
import sys
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
        data_transfer = event.get("dataTransfer")
        if not isinstance(data_transfer, dict):
            return
        files = data_transfer.get("files")
        if not isinstance(files, list) or not files:
            return
        first = files[0]
        if not isinstance(first, dict):
            return
        path = first.get("pywebviewFullPath")
        if not isinstance(path, str) or not path:
            return
        response = api.load_document(path)
        if not response["success"]:
            api.publish_bridge_error(response["error"])

    def install_drop_handler() -> None:
        drop_target = window.dom.get_element(".file-drop")
        if drop_target is not None:
            drop_target.events.drop += handle_drop

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
