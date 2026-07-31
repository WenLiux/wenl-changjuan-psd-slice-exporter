from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path

import pytest
from PIL import Image

import app.services.export_service as export_service_module
from app.models.composite_result import CompositeResult
from app.models.export_result import ExportOptions, ExportProgress
from app.models.slice_info import SliceInfo, SliceParseResult
from app.services.export_service import (
    ExportPreflightError,
    export_original_size,
    export_prepared_original_size,
    export_prepared_slices,
    export_slices,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads(
    (PROJECT_ROOT / "tests" / "fixtures" / "baseline_manifest.json").read_text(
        encoding="utf-8"
    )
)


def fixture_path(sample_name: str) -> Path:
    sample = MANIFEST[sample_name]
    environment_variable = sample["environment_variable"]
    value = os.environ.get(environment_variable)
    if not value:
        pytest.skip(f"{environment_variable} is not set")
    path = Path(value)
    if not path.is_file():
        pytest.fail(f"{environment_variable} does not point to a file: {path}")
    return path


def image_pixel_sha256(path: Path) -> str:
    with Image.open(path) as image:
        image.load()
        digest = hashlib.sha256()
        digest.update(image.mode.encode("ascii"))
        digest.update(f"{image.width}x{image.height}".encode("ascii"))
        digest.update(image.tobytes())
        return digest.hexdigest()


def prepared_document(
    source_path: Path,
    *,
    reliable: bool = True,
) -> tuple[SliceParseResult, CompositeResult]:
    source_path.write_bytes(b"fixture")
    slices = (
        SliceInfo(
            index=0,
            slice_id=1,
            name="top",
            left=0,
            top=0,
            right=10,
            bottom=10,
            is_automatic=False,
            source_version="V8",
            origin="userGenerated",
        ),
        SliceInfo(
            index=1,
            slice_id=2,
            name="bottom",
            left=0,
            top=10,
            right=10,
            bottom=20,
            is_automatic=False,
            source_version="V8",
            origin="userGenerated",
        ),
    )
    slice_result = SliceParseResult(
        source_version="V8",
        all_slices=slices,
        exportable_slices=slices,
        excluded_slices=(),
        issues=(),
    )
    composite = CompositeResult(
        image=Image.new("RGBA", (10, 20), (10, 20, 30, 128)),
        source=(
            "embedded_merged"
            if reliable
            else "embedded_merged_unverified"
        ),
        width=10,
        height=20,
        color_mode="RGB",
        depth=8,
        pil_mode="RGBA",
        icc_profile=None,
        has_alpha=True,
        is_reliable=reliable,
        warning=None if reliable else "Unverified composite.",
    )
    return slice_result, composite


@pytest.mark.parametrize("sample_name", ["psd_v8", "psb_v6"])
def test_real_fixture_original_export_matches_baseline(
    sample_name: str, tmp_path: Path
) -> None:
    source = fixture_path(sample_name)
    sample = MANIFEST[sample_name]
    source_stat = source.stat()

    result = export_original_size(
        source,
        ExportOptions(output_parent=tmp_path),
    )

    assert result.success
    assert result.status == "completed"
    assert result.archive_path is None
    assert result.source_unchanged
    assert result.validation_report.passed
    assert result.validation_json_path is not None
    assert result.validation_json_path.is_file()
    assert result.validation_text_path is not None
    assert result.validation_text_path.is_file()
    assert source.stat().st_size == source_stat.st_size
    assert source.stat().st_mtime_ns == source_stat.st_mtime_ns
    assert [item.output_path.name for item in result.exported_slices] == [
        record[0] for record in sample["outputs"]
    ]
    assert len(result.exported_slices) == 14

    for output_index in (0, len(sample["outputs"]) - 1):
        expected = sample["outputs"][output_index]
        output = result.exported_slices[output_index]
        assert [output.width, output.height, output.mode] == expected[1:4]
        assert image_pixel_sha256(output.output_path) == expected[4]


def test_output_directories_are_collision_safe_and_zip_is_opt_in(
    tmp_path: Path,
) -> None:
    source = tmp_path / "sample.psd"
    first_slices, first_composite = prepared_document(source)
    first = export_prepared_original_size(
        source,
        first_slices,
        first_composite,
        ExportOptions(output_parent=tmp_path),
    )

    second_slices, second_composite = prepared_document(source)
    second = export_prepared_original_size(
        source,
        second_slices,
        second_composite,
        ExportOptions(output_parent=tmp_path, create_zip=True),
    )

    assert first.output_directory.name == "sample_slices_original"
    assert first.archive_path is None
    assert second.output_directory.name == "sample_slices_original_02"
    assert second.archive_path is not None
    assert second.archive_path.is_file()
    with zipfile.ZipFile(second.archive_path) as archive:
        assert archive.testzip() is None
        assert sorted(archive.namelist()) == [
            "slice_01_10x10.png",
            "slice_02_10x10.png",
            "validation_report.json",
            "validation_report.txt",
        ]

    first_composite.image.close()
    second_composite.image.close()


def test_cancellation_is_checked_between_slices(tmp_path: Path) -> None:
    source = tmp_path / "cancel.psd"
    slices, composite = prepared_document(source)
    checks = 0
    progress: list[ExportProgress] = []

    def cancel_check() -> bool:
        nonlocal checks
        checks += 1
        return checks > 1

    result = export_prepared_original_size(
        source,
        slices,
        composite,
        ExportOptions(output_parent=tmp_path),
        progress_callback=progress.append,
        cancel_check=cancel_check,
    )

    assert result.status == "cancelled"
    assert len(result.exported_slices) == 1
    assert [item.phase for item in progress] == [
        "starting",
        "exporting",
        "written",
    ]
    assert not result.archive_path
    composite.image.close()


def test_unverified_composite_requires_explicit_permission(
    tmp_path: Path,
) -> None:
    source = tmp_path / "unverified.psd"
    slices, composite = prepared_document(source, reliable=False)

    with pytest.raises(ExportPreflightError, match="Unverified composite"):
        export_prepared_original_size(
            source,
            slices,
            composite,
            ExportOptions(output_parent=tmp_path),
        )

    allowed = export_prepared_original_size(
        source,
        slices,
        composite,
        ExportOptions(
            output_parent=tmp_path,
            allow_unverified_composite=True,
        ),
    )
    assert allowed.success
    composite.image.close()


def test_no_exportable_slices_is_a_preflight_error(tmp_path: Path) -> None:
    source = tmp_path / "empty.psd"
    slices, composite = prepared_document(source)
    empty_result = SliceParseResult(
        source_version="V8",
        all_slices=(),
        exportable_slices=(),
        excluded_slices=(),
        issues=(),
    )

    with pytest.raises(ExportPreflightError, match="no exportable slices"):
        export_prepared_original_size(
            source,
            empty_result,
            composite,
            ExportOptions(output_parent=tmp_path),
        )
    composite.image.close()


def test_prepared_target_width_export_reports_scale_and_strategy(
    tmp_path: Path,
) -> None:
    source = tmp_path / "target.psd"
    slices, composite = prepared_document(source)

    result = export_prepared_slices(
        source,
        slices,
        composite,
        ExportOptions(output_parent=tmp_path, target_width=5),
    )

    assert result.success
    assert result.target_width == 5
    assert result.scale == 0.5
    assert result.resize_strategy == "full_canvas"
    assert result.output_directory.name == "target_slices_5px"
    assert [(item.width, item.height) for item in result.exported_slices] == [
        (5, 5),
        (5, 5),
    ]
    composite.image.close()


def test_low_memory_strategy_matches_full_resize_for_solid_fixture(
    tmp_path: Path,
) -> None:
    source = tmp_path / "memory.psd"
    full_slices, full_composite = prepared_document(source)
    full = export_prepared_slices(
        source,
        full_slices,
        full_composite,
        ExportOptions(
            output_parent=tmp_path,
            target_width=7,
            max_full_resize_bytes=1024 * 1024,
        ),
    )

    low_slices, low_composite = prepared_document(source)
    low = export_prepared_slices(
        source,
        low_slices,
        low_composite,
        ExportOptions(
            output_parent=tmp_path,
            target_width=7,
            max_full_resize_bytes=1,
        ),
    )

    assert full.resize_strategy == "full_canvas"
    assert low.resize_strategy == "per_slice"
    assert [
        image_pixel_sha256(item.output_path) for item in full.exported_slices
    ] == [
        image_pixel_sha256(item.output_path) for item in low.exported_slices
    ]
    full_composite.image.close()
    low_composite.image.close()


def test_real_psd_exports_full_width_slices_at_750px(tmp_path: Path) -> None:
    source = fixture_path("psd_v8")

    result = export_slices(
        source,
        ExportOptions(output_parent=tmp_path, target_width=750),
    )

    assert result.success
    assert result.target_width == 750
    assert result.resize_strategy == "full_canvas"
    assert all(item.width == 750 for item in result.exported_slices)
    assert sum(item.height for item in result.exported_slices) == round(
        28164 * 750 / 1440
    )


def test_if_needed_photoshop_fallback_replaces_missing_composite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "fallback.psd"
    slices, embedded = prepared_document(source)
    embedded.image.close()
    missing = CompositeResult(
        image=None,
        source="missing",
        width=10,
        height=20,
        color_mode="RGB",
        depth=8,
        pil_mode=None,
        icc_profile=None,
        has_alpha=True,
        is_reliable=False,
        error="No embedded composite.",
    )
    photoshop = CompositeResult(
        image=Image.new("RGBA", (10, 20), (5, 6, 7, 128)),
        source="photoshop",
        width=10,
        height=20,
        color_mode="RGB",
        depth=8,
        pil_mode="RGBA",
        icc_profile=None,
        has_alpha=True,
        is_reliable=True,
    )
    calls: list[dict[str, object]] = []

    monkeypatch.setattr(
        export_service_module.PSDImage,
        "open",
        lambda path: object(),
    )
    monkeypatch.setattr(
        export_service_module,
        "parse_document_slices",
        lambda psd: slices,
    )
    monkeypatch.setattr(
        export_service_module,
        "read_embedded_composite",
        lambda psd: missing,
    )

    def fake_photoshop(
        path: Path,
        **kwargs: object,
    ) -> CompositeResult:
        calls.append({"path": path, **kwargs})
        return photoshop

    monkeypatch.setattr(
        export_service_module,
        "read_photoshop_composite",
        fake_photoshop,
    )

    result = export_slices(
        source,
        ExportOptions(
            output_parent=tmp_path,
            photoshop_fallback="if_needed",
        ),
    )

    assert result.success
    assert result.composite_source == "photoshop"
    assert result.composite_warning is not None
    assert "No embedded composite" in result.composite_warning
    assert len(calls) == 1
    assert calls[0]["path"] == source
    assert calls[0]["expected_has_alpha"] is True
    assert len(result.exported_slices) == 2


def test_disabled_photoshop_fallback_preserves_existing_failure_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "disabled.psd"
    slices, embedded = prepared_document(source)
    embedded.image.close()
    missing = CompositeResult(
        image=None,
        source="missing",
        width=10,
        height=20,
        color_mode="RGB",
        depth=8,
        pil_mode=None,
        icc_profile=None,
        has_alpha=False,
        is_reliable=False,
        error="No embedded composite.",
    )
    monkeypatch.setattr(
        export_service_module.PSDImage,
        "open",
        lambda path: object(),
    )
    monkeypatch.setattr(
        export_service_module,
        "parse_document_slices",
        lambda psd: slices,
    )
    monkeypatch.setattr(
        export_service_module,
        "read_embedded_composite",
        lambda psd: missing,
    )
    monkeypatch.setattr(
        export_service_module,
        "read_photoshop_composite",
        lambda *args, **kwargs: pytest.fail(
            "Photoshop must remain disabled by default."
        ),
    )

    with pytest.raises(
        ExportPreflightError,
        match="No embedded composite",
    ):
        export_slices(
            source,
            ExportOptions(output_parent=tmp_path),
        )


def test_if_needed_fallback_skips_reliable_embedded_composite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "reliable.psd"
    slices, composite = prepared_document(source)
    monkeypatch.setattr(
        export_service_module.PSDImage,
        "open",
        lambda path: object(),
    )
    monkeypatch.setattr(
        export_service_module,
        "parse_document_slices",
        lambda psd: slices,
    )
    monkeypatch.setattr(
        export_service_module,
        "read_embedded_composite",
        lambda psd: composite,
    )
    monkeypatch.setattr(
        export_service_module,
        "read_photoshop_composite",
        lambda *args, **kwargs: pytest.fail(
            "Reliable composites must not start Photoshop."
        ),
    )

    result = export_slices(
        source,
        ExportOptions(
            output_parent=tmp_path,
            photoshop_fallback="if_needed",
        ),
    )

    assert result.success
    assert result.composite_source == "embedded_merged"
