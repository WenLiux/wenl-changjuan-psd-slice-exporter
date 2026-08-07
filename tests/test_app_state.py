from __future__ import annotations

from pathlib import Path

import pytest

from app.models.app_settings import AppSettings
from app.models.prepared_document import DocumentSummary
from app.models.slice_info import SliceInfo
from app.ui.app_state import (
    FormValidationError,
    UiMode,
    build_export_options,
    derive_output_format_state,
    estimate_slice_outputs,
    parse_hex_rgb,
)


def _slice(
    index: int,
    name: str,
    top: int,
    bottom: int,
    *,
    right: int = 10,
) -> SliceInfo:
    return SliceInfo(
        index=index,
        slice_id=index + 100,
        name=name,
        left=0,
        top=top,
        right=right,
        bottom=bottom,
        is_automatic=False,
        source_version="V8",
    )


def _document(
    slices: tuple[SliceInfo, ...] | None = None,
) -> DocumentSummary:
    actual_slices = slices or (
        _slice(4, "top", 0, 7),
        _slice(9, "bottom", 7, 20),
    )
    return DocumentSummary(
        source_path=Path("detail.psb"),
        source_size=123,
        width=10,
        height=20,
        color_mode="RGB",
        depth=8,
        has_alpha=True,
        source_version="V8",
        slice_count=len(actual_slices),
        excluded_slice_count=0,
        slices=actual_slices,
        issues=(),
        composite_source="embedded_merged",
        composite_is_available=True,
        composite_is_reliable=True,
        composite_warning=None,
        composite_error=None,
        preparation_mode="disabled",
    )


def test_ui_modes_have_busy_and_cancel_semantics() -> None:
    assert UiMode.EMPTY.value == "empty"
    assert UiMode.READY.value == "ready"
    assert not UiMode.EMPTY.is_busy
    assert not UiMode.READY.is_busy
    assert UiMode.LOADING.is_busy
    assert UiMode.EXPORTING.can_cancel
    assert UiMode.LOADING.can_cancel
    assert not UiMode.CANCELLING.can_cancel
    assert UiMode.SHUTTING_DOWN.is_busy


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("#000000", (0, 0, 0)),
        ("#ffffff", (255, 255, 255)),
        ("  #12aBcF  ", (18, 171, 207)),
    ],
)
def test_parse_hex_rgb(value: str, expected: tuple[int, int, int]) -> None:
    assert parse_hex_rgb(value) == expected


@pytest.mark.parametrize(
    "value",
    ["FFFFFF", "#FFF", "#1234567", "#12GG00", "", " #12345 "],
)
def test_parse_hex_rgb_rejects_invalid_form_values(value: str) -> None:
    with pytest.raises(FormValidationError, match="#RRGGBB"):
        parse_hex_rgb(value)


def test_output_format_state_links_png_controls() -> None:
    state = derive_output_format_state("png")

    assert state.is_png
    assert not state.is_jpeg
    assert state.file_extension == ".png"
    assert not state.jpeg_quality_enabled
    assert not state.jpeg_background_enabled
    assert state.supports_transparency


def test_output_format_state_links_jpeg_controls() -> None:
    state = derive_output_format_state("JPG")

    assert state.is_jpeg
    assert not state.is_png
    assert state.file_extension == ".jpg"
    assert state.jpeg_quality_enabled
    assert state.jpeg_background_enabled
    assert not state.supports_transparency


def test_slice_estimates_use_global_rounding_and_keep_parser_index() -> None:
    estimates = estimate_slice_outputs(
        AppSettings(width_mode="custom", target_width=5),
        _document(),
    )

    assert [
        (
            item.index,
            item.slice_info.name,
            item.source_width,
            item.source_height,
            item.output_width,
            item.output_height,
        )
        for item in estimates
    ] == [
        (4, "top", 10, 7, 5, 4),
        (9, "bottom", 10, 13, 5, 6),
    ]


def test_slice_estimates_can_follow_current_selection() -> None:
    estimates = estimate_slice_outputs(
        AppSettings(),
        _document(),
        selected_slice_indices={9},
    )

    assert [
        (item.index, item.output_width, item.output_height)
        for item in estimates
    ] == [(9, 10, 13)]
    assert (
        estimate_slice_outputs(
            AppSettings(),
            _document(),
            selected_slice_indices=set(),
        )
        == ()
    )


def test_original_width_builds_complete_export_options(
    tmp_path: Path,
) -> None:
    output_directory = tmp_path / "new-output"
    settings = AppSettings(
        output_directory=tmp_path / "saved-but-not-current",
        width_mode="original",
        target_width=1440,
        allow_upscale=False,
        output_format="jpeg",
        jpeg_quality=88,
        jpeg_background="#123456",
        color_policy="srgb",
        create_zip=True,
        open_output_folder=False,
        naming_rule="slice_name_with_index",
        photoshop_fallback="if_needed",
    )

    options = build_export_options(
        settings,
        _document(),
        output_directory=output_directory,
        selected_slice_indices={9},
        photoshop_allow_launch=True,
        allow_mode_conversion=True,
        allow_unverified_composite=True,
    )

    assert options.output_parent == output_directory
    assert options.target_width is None
    assert not options.allow_upscale
    assert options.selected_slice_indices == frozenset({9})
    assert options.output_format == "jpeg"
    assert options.jpeg_quality == 88
    assert options.jpeg_background == (18, 52, 86)
    assert options.color_policy == "srgb"
    assert options.create_zip
    assert options.naming_rule == "slice_name_with_index"
    assert options.photoshop_fallback == "if_needed"
    assert options.photoshop_allow_launch
    assert options.allow_mode_conversion
    assert options.allow_unverified_composite


def test_custom_width_is_applied_and_none_selects_all(
    tmp_path: Path,
) -> None:
    options = build_export_options(
        AppSettings(width_mode="custom", target_width=5),
        _document(),
        output_directory=tmp_path,
        selected_slice_indices=None,
    )

    assert options.target_width == 5
    assert options.selected_slice_indices == frozenset({4, 9})


def test_full_canvas_options_do_not_require_slice_selection(
    tmp_path: Path,
) -> None:
    options = build_export_options(
        AppSettings(
            export_mode="full_canvas",
            width_mode="custom",
            target_width=5,
        ),
        _document(),
        output_directory=tmp_path,
        selected_slice_indices=set(),
    )

    assert options.export_mode == "full_canvas"
    assert options.target_width == 5
    assert options.selected_slice_indices is None


@pytest.mark.parametrize("value", [None, "", "   "])
def test_blank_output_directory_uses_source_parent(
    tmp_path: Path,
    value: Path | str | None,
) -> None:
    document = _document()
    document = DocumentSummary(
        **{
            field: getattr(document, field)
            for field in document.__dataclass_fields__
            if field != "source_path"
        },
        source_path=tmp_path / "source" / "detail.psb",
    )

    options = build_export_options(
        AppSettings(),
        document,
        output_directory=value,
        selected_slice_indices={4},
    )

    assert options.output_parent == document.source_path.parent


def test_export_rejects_file_as_output_directory(tmp_path: Path) -> None:
    output_file = tmp_path / "file.txt"
    output_file.write_text("not a directory", encoding="utf-8")

    with pytest.raises(FormValidationError, match="not a directory"):
        build_export_options(
            AppSettings(),
            _document(),
            output_directory=output_file,
            selected_slice_indices={4},
        )


def test_export_requires_at_least_one_slice(tmp_path: Path) -> None:
    with pytest.raises(FormValidationError, match="at least one"):
        build_export_options(
            AppSettings(),
            _document(),
            output_directory=tmp_path,
            selected_slice_indices=set(),
        )


def test_export_rejects_unknown_slice_index(tmp_path: Path) -> None:
    with pytest.raises(FormValidationError, match="Unknown slice index: 7"):
        build_export_options(
            AppSettings(),
            _document(),
            output_directory=tmp_path,
            selected_slice_indices={7},
        )


def test_export_validates_width_against_no_upscale(tmp_path: Path) -> None:
    with pytest.raises(FormValidationError, match="upscaling is disabled"):
        build_export_options(
            AppSettings(
                width_mode="custom",
                target_width=20,
                allow_upscale=False,
            ),
            _document(),
            output_directory=tmp_path,
            selected_slice_indices={4},
        )


def test_one_time_safety_grants_must_be_booleans(
    tmp_path: Path,
) -> None:
    with pytest.raises(TypeError, match="photoshop_allow_launch"):
        build_export_options(
            AppSettings(),
            _document(),
            output_directory=tmp_path,
            selected_slice_indices={4},
            photoshop_allow_launch=1,  # type: ignore[arg-type]
        )
