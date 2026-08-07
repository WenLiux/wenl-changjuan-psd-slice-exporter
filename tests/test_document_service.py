from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image

from app.core.slice_parser import SliceResourceMissingError
import app.services.document_service as document_service_module
from app.models.composite_result import CompositeResult
from app.models.export_result import ExportOptions
from app.models.slice_info import SliceInfo, SliceParseResult
from app.services.document_service import (
    build_document_load_result,
    export_prepared_document,
    prepare_document,
)
from app.services.errors import ExportPreflightError


def _slice_result() -> SliceParseResult:
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
        ),
    )
    return SliceParseResult(
        source_version="V8",
        all_slices=slices,
        exportable_slices=slices,
        excluded_slices=(),
        issues=(),
    )


def _composite() -> CompositeResult:
    return CompositeResult(
        image=Image.new("RGBA", (10, 20), (20, 30, 40, 128)),
        source="embedded_merged",
        width=10,
        height=20,
        color_mode="RGB",
        depth=8,
        pil_mode="RGBA",
        icc_profile=None,
        has_alpha=True,
        is_reliable=True,
    )


def _patch_preparation(
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, int]:
    calls = {"open": 0, "parse": 0, "composite": 0}

    def open_psd(path: Path) -> object:
        calls["open"] += 1
        return object()

    def parse(psd: object) -> SliceParseResult:
        calls["parse"] += 1
        return _slice_result()

    def read(psd: object) -> CompositeResult:
        calls["composite"] += 1
        return _composite()

    monkeypatch.setattr(document_service_module.PSDImage, "open", open_psd)
    monkeypatch.setattr(
        document_service_module,
        "parse_document_slices",
        parse,
    )
    monkeypatch.setattr(
        document_service_module,
        "read_embedded_composite",
        read,
    )
    return calls


def test_prepared_document_is_reused_for_multiple_exports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "中文 sample.psd"
    source.write_bytes(b"fixture")
    calls = _patch_preparation(monkeypatch)

    with prepare_document(source) as prepared:
        summary = prepared.summary
        first = export_prepared_document(
            prepared,
            ExportOptions(output_parent=tmp_path, target_width=10),
        )
        second = export_prepared_document(
            prepared,
            ExportOptions(output_parent=tmp_path, target_width=5),
        )

        assert summary.source_path == source
        assert summary.slice_count == 2
        assert summary.slices == _slice_result().exportable_slices
        assert first.target_width == 10
        assert second.target_width == 5

    assert calls == {"open": 1, "parse": 1, "composite": 1}
    assert prepared.closed


def test_missing_slice_resource_still_allows_full_canvas_export(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "without-slices.psd"
    source.write_bytes(b"fixture")
    _patch_preparation(monkeypatch)
    monkeypatch.setattr(
        document_service_module,
        "parse_document_slices",
        lambda psd: (_ for _ in ()).throw(
            SliceResourceMissingError("no slices")
        ),
    )

    with prepare_document(source) as prepared:
        assert prepared.summary.slice_count == 0
        assert prepared.summary.issues[0].code == "no_slice_resource"
        assert build_document_load_result(prepared).preview_png is not None
        result = export_prepared_document(
            prepared,
            ExportOptions(
                output_parent=tmp_path,
                export_mode="full_canvas",
            ),
        )

    assert result.success
    assert result.output_path is not None


def test_changed_source_rejects_cached_document(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "changed.psd"
    source.write_bytes(b"before")
    _patch_preparation(monkeypatch)

    with prepare_document(source) as prepared:
        source.write_bytes(b"after")
        with pytest.raises(
            ExportPreflightError,
            match="changed after it was loaded",
        ):
            export_prepared_document(
                prepared,
                ExportOptions(output_parent=tmp_path),
            )


def test_photoshop_mode_change_requires_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "mode.psd"
    source.write_bytes(b"fixture")
    _patch_preparation(monkeypatch)

    with prepare_document(source) as prepared:
        with pytest.raises(ExportPreflightError, match="setting changed"):
            export_prepared_document(
                prepared,
                ExportOptions(
                    output_parent=tmp_path,
                    photoshop_fallback="always",
                ),
            )


def test_reliable_embedded_cache_is_compatible_with_if_needed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "compatible.psd"
    source.write_bytes(b"fixture")
    _patch_preparation(monkeypatch)

    with prepare_document(source) as prepared:
        result = export_prepared_document(
            prepared,
            ExportOptions(
                output_parent=tmp_path,
                photoshop_fallback="if_needed",
            ),
        )

    assert result.success


def test_document_load_result_contains_only_small_preview_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "preview.psd"
    source.write_bytes(b"fixture")
    _patch_preparation(monkeypatch)

    with prepare_document(source) as prepared:
        result = build_document_load_result(
            prepared,
            preview_size=(5, 5),
        )

    assert result.summary.source_path == source
    assert result.preview_slice_index == 0
    assert isinstance(result.preview_png, bytes)
    with Image.open(BytesIO(result.preview_png)) as preview:
        assert preview.width <= 5
        assert preview.height <= 5
