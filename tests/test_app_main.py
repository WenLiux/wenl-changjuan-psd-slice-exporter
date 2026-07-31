from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.main as main_module
from app.models.composite_result import CompositeResult
from app.models.export_result import ExportOptions
from app.models.slice_info import SliceInfo, SliceParseResult
from app.services.export_service import export_prepared_slices


def _successful_export(tmp_path: Path):
    source = tmp_path / "sample.psd"
    source.write_bytes(b"fixture")
    slice_info = SliceInfo(
        index=0,
        slice_id=1,
        name="slice",
        left=0,
        top=0,
        right=10,
        bottom=10,
        is_automatic=False,
        source_version="V8",
    )
    slices = SliceParseResult(
        source_version="V8",
        all_slices=(slice_info,),
        exportable_slices=(slice_info,),
        excluded_slices=(),
        issues=(),
    )
    from PIL import Image

    composite = CompositeResult(
        image=Image.new("RGB", (10, 10), (1, 2, 3)),
        source="embedded_merged",
        width=10,
        height=10,
        color_mode="RGB",
        depth=8,
        pil_mode="RGB",
        icc_profile=None,
        has_alpha=False,
        is_reliable=True,
    )
    result = export_prepared_slices(
        source,
        slices,
        composite,
        ExportOptions(output_parent=tmp_path),
    )
    composite.image.close()
    return result


def test_package_smoke_writes_machine_readable_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _successful_export(tmp_path)
    result_path = tmp_path / "smoke.json"
    monkeypatch.setattr(
        main_module,
        "_probe_photoshop_bindings",
        lambda: (True, None),
    )
    monkeypatch.setattr(
        main_module,
        "_probe_tkdnd",
        lambda: (True, "2.10.1"),
    )
    monkeypatch.setattr(
        main_module,
        "export_slices",
        lambda source, options: result,
    )

    return_code = main_module.run_package_smoke(
        tmp_path / "sample.psd",
        tmp_path,
        result_path,
        target_width=750,
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert return_code == 0
    assert payload["success"] is True
    assert payload["slice_count"] == 1
    assert payload["photoshop_bindings_available"] is True
    assert payload["tkdnd_available"] is True


def test_package_smoke_records_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_path = tmp_path / "failed.json"
    monkeypatch.setattr(
        main_module,
        "_probe_photoshop_bindings",
        lambda: (True, None),
    )
    monkeypatch.setattr(
        main_module,
        "_probe_tkdnd",
        lambda: (True, "2.10.1"),
    )
    monkeypatch.setattr(
        main_module,
        "export_slices",
        lambda source, options: (_ for _ in ()).throw(
            RuntimeError("simulated failure")
        ),
    )

    return_code = main_module.run_package_smoke(
        tmp_path / "sample.psd",
        tmp_path,
        result_path,
        target_width=750,
    )

    payload = json.loads(result_path.read_text(encoding="utf-8"))
    assert return_code == 1
    assert payload["status"] == "failed"
    assert payload["error_type"] == "RuntimeError"
    assert "simulated failure" in payload["traceback"]
