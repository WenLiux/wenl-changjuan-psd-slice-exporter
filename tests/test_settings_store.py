from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.models.app_settings import AppSettings
from app.services.settings_store import (
    SETTINGS_DIRECTORY_NAME,
    SETTINGS_FILE_NAME,
    SETTINGS_SCHEMA_VERSION,
    SettingsStore,
    default_settings_path,
)


def test_default_path_uses_appdata_without_creating_it(
    tmp_path: Path,
) -> None:
    appdata = tmp_path / "Roaming"

    result = default_settings_path({"APPDATA": str(appdata)})

    assert result == (
        appdata / SETTINGS_DIRECTORY_NAME / SETTINGS_FILE_NAME
    )
    assert not appdata.exists()


def test_round_trip_writes_versioned_json(tmp_path: Path) -> None:
    path = tmp_path / "偏好" / "settings.json"
    expected = AppSettings(
        output_directory=tmp_path / "导出",
        width_mode="custom",
        target_width=1440,
        allow_upscale=False,
        output_format="jpeg",
        jpeg_quality=91,
        jpeg_background="#F5F5F5",
        color_policy="srgb",
        create_zip=True,
        open_output_folder=False,
        naming_rule="sequence_dimensions",
        photoshop_fallback="if_needed",
    )
    store = SettingsStore(path)

    saved_path = store.save(expected)
    loaded = store.load_with_diagnostics()

    assert saved_path == path
    assert loaded.settings == expected
    assert not loaded.used_defaults
    assert loaded.warnings == ()
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["schema_version"] == SETTINGS_SCHEMA_VERSION
    assert document["settings"]["output_directory"] == str(
        expected.output_directory
    )


def test_missing_file_returns_defaults_without_warnings(
    tmp_path: Path,
) -> None:
    defaults = AppSettings(target_width=1920, create_zip=True)
    result = SettingsStore(
        tmp_path / "missing.json",
        defaults=defaults,
    ).load_with_diagnostics()

    assert result.settings is defaults
    assert result.used_defaults
    assert result.warnings == ()


@pytest.mark.parametrize(
    "contents",
    [
        "{broken",
        "[]",
        json.dumps(
            {
                "schema_version": SETTINGS_SCHEMA_VERSION + 1,
                "settings": {},
            }
        ),
        json.dumps(
            {
                "schema_version": SETTINGS_SCHEMA_VERSION,
                "settings": [],
            }
        ),
    ],
)
def test_corrupt_document_falls_back_safely(
    tmp_path: Path,
    contents: str,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(contents, encoding="utf-8")
    defaults = AppSettings(target_width=2048)

    result = SettingsStore(path, defaults=defaults).load_with_diagnostics()

    assert result.settings == defaults
    assert result.used_defaults
    assert result.warnings


def test_invalid_utf8_falls_back_safely(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_bytes(b"\xff\xfe\x00")

    result = SettingsStore(path).load_with_diagnostics()

    assert result.settings == AppSettings()
    assert result.used_defaults
    assert result.warnings


def test_invalid_fields_fall_back_individually(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": SETTINGS_SCHEMA_VERSION,
                "settings": {
                    "output_directory": "",
                    "width_mode": "custom",
                    "target_width": True,
                    "allow_upscale": "yes",
                    "output_format": "JPG",
                    "jpeg_quality": 101,
                    "jpeg_background": "white",
                    "color_policy": "srgb",
                    "create_zip": "yes",
                    "open_output_folder": False,
                    "naming_rule": "not-a-rule",
                    "photoshop_fallback": "always",
                },
            }
        ),
        encoding="utf-8",
    )

    result = SettingsStore(path).load_with_diagnostics()

    assert result.settings == AppSettings(
        width_mode="custom",
        output_format="jpeg",
        color_policy="srgb",
        open_output_folder=False,
        photoshop_fallback="always",
    )
    assert result.used_defaults
    assert len(result.warnings) == 7
    assert all("used its default" in warning for warning in result.warnings)


def test_missing_fields_use_custom_defaults_without_warning(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": SETTINGS_SCHEMA_VERSION,
                "settings": {"target_width": 1600},
            }
        ),
        encoding="utf-8",
    )
    defaults = AppSettings(
        output_format="jpeg",
        create_zip=True,
        target_width=1440,
    )

    result = SettingsStore(path, defaults=defaults).load_with_diagnostics()

    assert result.settings.target_width == 1600
    assert result.settings.output_format == "jpeg"
    assert result.settings.create_zip
    assert not result.used_defaults
    assert result.warnings == ()


def test_failed_atomic_replace_preserves_existing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "settings.json"
    original = b'{"previous": true}\n'
    path.write_bytes(original)
    store = SettingsStore(path)

    def fail_replace(source: Path, destination: Path) -> None:
        assert source.parent == destination.parent == tmp_path
        raise PermissionError("simulated replace failure")

    monkeypatch.setattr(
        "app.services.settings_store.os.replace",
        fail_replace,
    )

    with pytest.raises(PermissionError, match="replace failure"):
        store.save(AppSettings(target_width=1920))

    assert path.read_bytes() == original
    assert list(tmp_path.glob(".settings.json.*.tmp")) == []


@pytest.mark.parametrize(
    ("field", "value", "error_type"),
    [
        ("width_mode", "wrong", ValueError),
        ("target_width", 0, ValueError),
        ("target_width", True, ValueError),
        ("allow_upscale", 1, TypeError),
        ("output_format", "gif", ValueError),
        ("jpeg_quality", 101, ValueError),
        ("jpeg_background", "white", ValueError),
        ("create_zip", 1, TypeError),
        ("naming_rule", "wrong", ValueError),
        ("photoshop_fallback", "wrong", ValueError),
    ],
)
def test_app_settings_rejects_invalid_programmatic_values(
    field: str,
    value: object,
    error_type: type[Exception],
) -> None:
    with pytest.raises(error_type):
        AppSettings(**{field: value})
