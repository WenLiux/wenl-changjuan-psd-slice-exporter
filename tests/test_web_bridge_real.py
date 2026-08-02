from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from app.bridge.api import AppApi
from app.services.settings_store import SettingsStore


@pytest.mark.skipif(
    not os.environ.get("PSD_SLICE_WEB_FIXTURE"),
    reason="PSD_SLICE_WEB_FIXTURE is not set.",
)
def test_real_document_loads_and_exports_through_web_bridge(
    tmp_path: Path,
) -> None:
    source = Path(os.environ["PSD_SLICE_WEB_FIXTURE"])
    if not source.is_file():
        pytest.fail(f"PSD_SLICE_WEB_FIXTURE does not exist: {source}")

    api = AppApi(SettingsStore(tmp_path / "settings.json"))
    events: list[dict[str, object]] = []
    api._event_sink = events.append
    try:
        response = api.load_document(str(source))
        assert response["success"] is True
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            if any(event["type"] == "document_loaded" for event in events):
                break
            if any(event["type"] == "task_failed" for event in events):
                pytest.fail(str(events[-1]))
            time.sleep(0.02)
        else:
            pytest.fail("Web bridge document load timed out.")

        document_event = next(
            event for event in events if event["type"] == "document_loaded"
        )
        document = document_event["document"]
        assert isinstance(document, dict)
        assert document["slice_count"] > 0
        assert str(document["preview_url"]).startswith("file:///")

        settings = api.get_initial_state()["data"]["settings"]
        settings.update(
            {
                "output_directory": str(tmp_path / "Web UI 输出"),
                "width_mode": "custom",
                "target_width": 750,
                "open_output_folder": False,
            }
        )
        selected = [item["index"] for item in document["slices"]]
        response = api.start_export(
            {
                "settings": settings,
                "selected_slice_indices": selected,
            }
        )
        assert response["success"] is True
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            terminal = [
                event
                for event in events
                if event["type"] in {
                    "export_completed",
                    "task_failed",
                    "task_cancelled",
                }
            ]
            if terminal:
                break
            time.sleep(0.02)
        else:
            pytest.fail("Web bridge export timed out.")

        assert terminal[-1]["type"] == "export_completed"
        result = terminal[-1]["result"]
        assert isinstance(result, dict)
        assert result["success"] is True
        assert result["target_width"] == 750
        assert result["exported_count"] == document["slice_count"]
        assert result["validation_passed"] is True
    finally:
        api.close()
