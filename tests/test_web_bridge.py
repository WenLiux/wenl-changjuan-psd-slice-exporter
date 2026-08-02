from __future__ import annotations

from pathlib import Path

from app import __version__
from app.bridge.api import AppApi
from app.services.settings_store import SettingsStore


def test_initial_state_is_json_safe(tmp_path: Path) -> None:
    api = AppApi(SettingsStore(tmp_path / "settings.json"))
    try:
        response = api.get_initial_state()
        assert response["success"] is True
        assert response["data"]["version"] == __version__
        assert response["data"]["settings"]["target_width"] == 1440
        assert response["data"]["settings"]["output_directory"] == ""
    finally:
        api.close()


def test_invalid_document_returns_structured_error(tmp_path: Path) -> None:
    api = AppApi(SettingsStore(tmp_path / "settings.json"))
    try:
        response = api.load_document(str(tmp_path / "missing.psd"))
        assert response == {
            "success": False,
            "data": None,
            "error": {
                "code": "INVALID_SOURCE_FILE",
                "message": "请选择存在的 PSD 或 PSB 文件。",
                "details": "",
            },
        }
    finally:
        api.close()


def test_settings_round_trip_through_bridge(tmp_path: Path) -> None:
    store = SettingsStore(tmp_path / "settings.json")
    api = AppApi(store)
    try:
        payload = api.get_initial_state()["data"]["settings"]
        payload.update(
            {
                "width_mode": "custom",
                "target_width": 750,
                "output_format": "jpeg",
                "jpeg_quality": 91,
                "output_directory": str(tmp_path / "输出 目录"),
                "open_output_folder": False,
            }
        )
        response = api.save_settings(payload)
        assert response["success"] is True
        saved = store.load()
        assert saved.target_width == 750
        assert saved.output_format == "jpeg"
        assert saved.output_directory == tmp_path / "输出 目录"
    finally:
        api.close()
