from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

import app.ui.main_window as main_window_module
from app.models.app_settings import AppSettings
from app.services.settings_store import SettingsStore
from app.ui.main_window import MainWindow


@pytest.mark.skipif(
    os.environ.get("PSD_SLICE_GUI_SMOKE") != "1",
    reason="Set PSD_SLICE_GUI_SMOKE=1 for the real Windows GUI smoke test.",
)
def test_real_psd_loads_resizes_view_and_closes_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_value = os.environ.get("PSD_SLICE_V8_FIXTURE")
    if not source_value:
        pytest.skip("PSD_SLICE_V8_FIXTURE is not set.")
    source = Path(source_value)
    if not source.is_file():
        pytest.fail(f"PSD_SLICE_V8_FIXTURE does not exist: {source}")

    dialogs: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_window_module.messagebox,
        "showerror",
        lambda title, message, **kwargs: dialogs.append((title, message)),
    )
    store = SettingsStore(
        tmp_path / "settings.json",
        defaults=AppSettings(open_output_folder=False),
    )
    app = MainWindow(settings_store=store)
    app.withdraw()
    try:
        app.update_idletasks()
        assert app.winfo_reqwidth() <= app.winfo_screenwidth()
        assert app.winfo_reqheight() <= app.winfo_screenheight()

        app._start_load(source)
        deadline = time.monotonic() + 45
        while app._active_task_id is not None and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)

        assert not dialogs
        assert app._summary is not None
        assert (app._summary.width, app._summary.height) == (1440, 28164)
        assert app._summary.slice_count == 14
        assert len(app._slice_rows) == 14

        app.width_mode_var.set("指定宽度")
        app.target_width_var.set("750")
        app.update()
        output_labels = [
            label.cget("text") for _, label in app._slice_rows.values()
        ]
        assert all("→ 750×" in text for text in output_labels)

        app.output_directory_var.set(str(tmp_path / "exports"))
        app.open_output_var.set(False)
        app._start_export(app._build_export_options())
        deadline = time.monotonic() + 45
        while app._active_task_id is not None and time.monotonic() < deadline:
            app.update()
            time.sleep(0.01)

        assert not dialogs
        assert app._last_result is not None
        assert app._last_result.success
        assert app._last_result.target_width == 750
        assert len(app._last_result.exported_slices) == 14
    finally:
        app._on_close()
        deadline = time.monotonic() + 10
        while app._runner.worker_alive and time.monotonic() < deadline:
            try:
                app.update()
            except Exception:
                break
            time.sleep(0.01)
        assert not app._runner.worker_alive
