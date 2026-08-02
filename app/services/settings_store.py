from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, TypeVar

from app.models.app_settings import AppSettings
from app.config.brand import (
    APP_DIRECTORY,
    APP_VENDOR_DIRECTORY,
    LEGACY_APP_DIRECTORY,
)


SETTINGS_SCHEMA_VERSION = 1
SETTINGS_VENDOR_NAME = APP_VENDOR_DIRECTORY
SETTINGS_DIRECTORY_NAME = APP_DIRECTORY
LEGACY_SETTINGS_DIRECTORY_NAME = LEGACY_APP_DIRECTORY
SETTINGS_FILE_NAME = "settings.json"

_T = TypeVar("_T")


@dataclass(frozen=True, slots=True)
class SettingsLoadResult:
    """Settings plus non-fatal recovery information for the UI."""

    settings: AppSettings
    path: Path
    used_defaults: bool
    warnings: tuple[str, ...] = ()
    migrated_from: Path | None = None


def default_settings_path(
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Return the settings path under the Windows roaming AppData folder."""

    environment = os.environ if environ is None else environ
    appdata_value = environment.get("APPDATA", "").strip()
    if appdata_value:
        appdata = Path(appdata_value)
    else:
        appdata = Path.home() / "AppData" / "Roaming"
    return (
        appdata
        / SETTINGS_VENDOR_NAME
        / SETTINGS_DIRECTORY_NAME
        / SETTINGS_FILE_NAME
    )


def legacy_settings_path(
    environ: Mapping[str, str] | None = None,
) -> Path:
    """Return the read-only compatibility path used before WENL branding."""

    environment = os.environ if environ is None else environ
    appdata_value = environment.get("APPDATA", "").strip()
    if appdata_value:
        appdata = Path(appdata_value)
    else:
        appdata = Path.home() / "AppData" / "Roaming"
    return appdata / LEGACY_SETTINGS_DIRECTORY_NAME / SETTINGS_FILE_NAME


class SettingsStore:
    """Versioned JSON persistence with field-level recovery and atomic saves."""

    def __init__(
        self,
        path: Path | None = None,
        *,
        defaults: AppSettings | None = None,
    ) -> None:
        self.path = path if path is not None else default_settings_path()
        self._legacy_path = legacy_settings_path() if path is None else None
        self.defaults = defaults if defaults is not None else AppSettings()

    def load(self) -> AppSettings:
        return self.load_with_diagnostics().settings

    def load_with_diagnostics(self) -> SettingsLoadResult:
        read_path = self.path
        migrated_from: Path | None = None
        if (
            not read_path.exists()
            and self._legacy_path is not None
            and self._legacy_path.is_file()
        ):
            read_path = self._legacy_path
            migrated_from = read_path
        try:
            serialized = read_path.read_text(encoding="utf-8-sig")
        except FileNotFoundError:
            return SettingsLoadResult(
                settings=self.defaults,
                path=self.path,
                used_defaults=True,
            )
        except (OSError, UnicodeError) as error:
            return SettingsLoadResult(
                settings=self.defaults,
                path=self.path,
                used_defaults=True,
                warnings=(f"Settings could not be read: {error}",),
            )

        try:
            document = json.loads(serialized)
        except (json.JSONDecodeError, UnicodeError) as error:
            return SettingsLoadResult(
                settings=self.defaults,
                path=self.path,
                used_defaults=True,
                warnings=(f"Settings JSON is invalid: {error}",),
            )

        if not isinstance(document, dict):
            return SettingsLoadResult(
                settings=self.defaults,
                path=self.path,
                used_defaults=True,
                warnings=("Settings root must be a JSON object.",),
            )
        version = document.get("schema_version")
        if (
            isinstance(version, bool)
            or not isinstance(version, int)
            or version != SETTINGS_SCHEMA_VERSION
        ):
            return SettingsLoadResult(
                settings=self.defaults,
                path=self.path,
                used_defaults=True,
                warnings=(
                    "Unsupported settings schema version "
                    f"{version!r}; expected {SETTINGS_SCHEMA_VERSION}.",
                ),
            )
        values = document.get("settings")
        if not isinstance(values, dict):
            return SettingsLoadResult(
                settings=self.defaults,
                path=self.path,
                used_defaults=True,
                warnings=("The settings value must be a JSON object.",),
            )

        settings, warnings = _decode_settings(values, self.defaults)
        if migrated_from is not None:
            try:
                self.save(settings)
            except OSError as error:
                warnings = (
                    *warnings,
                    f"旧版设置已读取，但无法迁移到新目录：{error}",
                )
        return SettingsLoadResult(
            settings=settings,
            path=self.path,
            used_defaults=bool(warnings),
            warnings=warnings,
            migrated_from=migrated_from,
        )

    def save(self, settings: AppSettings) -> Path:
        if not isinstance(settings, AppSettings):
            raise TypeError("settings must be an AppSettings instance.")

        document = {
            "schema_version": SETTINGS_SCHEMA_VERSION,
            "settings": _encode_settings(settings),
        }
        serialized = json.dumps(
            document,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"

        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.path.parent / (
            f".{self.path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            with temporary_path.open(
                "x",
                encoding="utf-8",
                newline="\n",
            ) as temporary_file:
                temporary_file.write(serialized)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, self.path)
        finally:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
        return self.path


def load_settings(path: Path | None = None) -> AppSettings:
    """Convenience wrapper for callers that do not need diagnostics."""

    return SettingsStore(path).load()


def save_settings(
    settings: AppSettings,
    path: Path | None = None,
) -> Path:
    """Convenience wrapper for atomically persisting settings."""

    return SettingsStore(path).save(settings)


def _encode_settings(settings: AppSettings) -> dict[str, Any]:
    values = asdict(settings)
    output_directory = settings.output_directory
    values["output_directory"] = (
        str(output_directory) if output_directory is not None else None
    )
    return values


def _decode_settings(
    values: dict[str, Any],
    defaults: AppSettings,
) -> tuple[AppSettings, tuple[str, ...]]:
    warnings: list[str] = []

    output_directory = _read_field(
        values,
        "output_directory",
        defaults.output_directory,
        _decode_output_directory,
        warnings,
    )
    width_mode = _read_field(
        values,
        "width_mode",
        defaults.width_mode,
        lambda value: _decode_choice(
            value,
            {"original", "custom"},
            "width_mode",
        ),
        warnings,
    )
    target_width = _read_field(
        values,
        "target_width",
        defaults.target_width,
        lambda value: _decode_integer(
            value,
            "target_width",
            minimum=1,
        ),
        warnings,
    )
    allow_upscale = _read_field(
        values,
        "allow_upscale",
        defaults.allow_upscale,
        lambda value: _decode_boolean(value, "allow_upscale"),
        warnings,
    )
    output_format = _read_field(
        values,
        "output_format",
        defaults.output_format,
        _decode_output_format,
        warnings,
    )
    jpeg_quality = _read_field(
        values,
        "jpeg_quality",
        defaults.jpeg_quality,
        lambda value: _decode_integer(
            value,
            "jpeg_quality",
            minimum=1,
            maximum=100,
        ),
        warnings,
    )
    jpeg_background = _read_field(
        values,
        "jpeg_background",
        defaults.jpeg_background,
        _decode_hex_color,
        warnings,
    )
    color_policy = _read_field(
        values,
        "color_policy",
        defaults.color_policy,
        lambda value: _decode_choice(
            value,
            {"auto", "preserve", "srgb"},
            "color_policy",
        ),
        warnings,
    )
    create_zip = _read_field(
        values,
        "create_zip",
        defaults.create_zip,
        lambda value: _decode_boolean(value, "create_zip"),
        warnings,
    )
    open_output_folder = _read_field(
        values,
        "open_output_folder",
        defaults.open_output_folder,
        lambda value: _decode_boolean(value, "open_output_folder"),
        warnings,
    )
    naming_rule = _read_field(
        values,
        "naming_rule",
        defaults.naming_rule,
        lambda value: _decode_choice(
            value,
            {
                "sequence_dimensions",
                "slice_name",
                "slice_name_with_index",
            },
            "naming_rule",
        ),
        warnings,
    )
    photoshop_fallback = _read_field(
        values,
        "photoshop_fallback",
        defaults.photoshop_fallback,
        lambda value: _decode_choice(
            value,
            {"disabled", "if_needed", "always"},
            "photoshop_fallback",
        ),
        warnings,
    )

    return (
        AppSettings(
            output_directory=output_directory,
            width_mode=width_mode,
            target_width=target_width,
            allow_upscale=allow_upscale,
            output_format=output_format,
            jpeg_quality=jpeg_quality,
            jpeg_background=jpeg_background,
            color_policy=color_policy,
            create_zip=create_zip,
            open_output_folder=open_output_folder,
            naming_rule=naming_rule,
            photoshop_fallback=photoshop_fallback,
        ),
        tuple(warnings),
    )


def _read_field(
    values: dict[str, Any],
    name: str,
    default: _T,
    decoder: Callable[[Any], _T],
    warnings: list[str],
) -> _T:
    if name not in values:
        return default
    try:
        return decoder(values[name])
    except (TypeError, ValueError) as error:
        warnings.append(f"{name} used its default: {error}")
        return default


def _decode_output_directory(value: Any) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        raise ValueError("output_directory must be a non-empty path or null")
    return Path(value.strip())


def _decode_output_format(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError("output_format must be a string")
    normalized = value.lower()
    if normalized == "jpg":
        normalized = "jpeg"
    if normalized not in {"png", "jpeg"}:
        raise ValueError("output_format must be png or jpeg")
    return normalized


def _decode_hex_color(value: Any) -> str:
    if not isinstance(value, str):
        raise TypeError("jpeg_background must be a string")
    normalized = value.strip().upper()
    if (
        len(normalized) != 7
        or not normalized.startswith("#")
    ):
        raise ValueError("jpeg_background must use #RRGGBB notation")
    try:
        int(normalized[1:], 16)
    except ValueError as error:
        raise ValueError(
            "jpeg_background must use #RRGGBB notation"
        ) from error
    return normalized


def _decode_choice(
    value: Any,
    choices: set[str],
    field_name: str,
) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    normalized = value.lower()
    if normalized not in choices:
        raise ValueError(
            f"{field_name} must be one of {', '.join(sorted(choices))}"
        )
    return normalized


def _decode_integer(
    value: Any,
    field_name: str,
    *,
    minimum: int,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer")
    if value < minimum or (maximum is not None and value > maximum):
        if maximum is None:
            raise ValueError(f"{field_name} must be at least {minimum}")
        raise ValueError(
            f"{field_name} must be between {minimum} and {maximum}"
        )
    return value


def _decode_boolean(value: Any, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a boolean")
    return value
