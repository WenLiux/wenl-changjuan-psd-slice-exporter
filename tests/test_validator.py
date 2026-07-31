from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from app.core.validator import validate_export_outputs, validate_slice_layout
from app.models.composite_result import CompositeResult
from app.models.export_result import ExportedSlice
from app.models.scale_plan import MappedSlice
from app.models.slice_info import SliceInfo
from app.models.validation_report import ValidationFinding, ValidationReport


def slice_info(
    index: int,
    bounds: tuple[int, int, int, int],
) -> SliceInfo:
    return SliceInfo(
        index=index,
        slice_id=index + 1,
        name="",
        left=bounds[0],
        top=bounds[1],
        right=bounds[2],
        bottom=bounds[3],
        is_automatic=False,
        source_version="V8",
        origin="userGenerated",
    )


def test_layout_reports_gaps_overlaps_and_duplicates() -> None:
    slices = [
        slice_info(0, (0, 0, 100, 40)),
        slice_info(1, (0, 30, 100, 60)),
        slice_info(2, (0, 70, 100, 100)),
        slice_info(3, (0, 70, 100, 100)),
    ]

    report = validate_slice_layout(
        slices,
        canvas_width=100,
        canvas_height=100,
    )

    codes = {item.code for item in report.findings}
    assert "overlap" in codes
    assert "duplicate_bounds" in codes
    assert "vertical_gap" in codes
    assert report.passed
    assert report.warning_count >= 3


def test_post_export_detects_pixel_mismatch(tmp_path: Path) -> None:
    source_image = Image.new("RGBA", (10, 20), (1, 2, 3, 255))
    composite = CompositeResult(
        image=source_image,
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
    info = slice_info(0, (0, 0, 10, 20))
    mapped = MappedSlice(info, 0, 0, 10, 20)
    output = tmp_path / "slice.png"
    Image.new("RGBA", (10, 20), (9, 9, 9, 255)).save(output)
    exported = ExportedSlice(info, output, 10, 20, "RGBA", output.stat().st_size)

    report = validate_export_outputs(
        [mapped],
        [exported],
        [],
        composite=composite,
        original_size=True,
    )

    assert "pixel_mismatch" in {item.code for item in report.findings}
    assert not report.passed
    source_image.close()


def test_validation_report_writes_json_and_text(tmp_path: Path) -> None:
    report = ValidationReport(
        (
            ValidationFinding(
                phase="preflight",
                code="example",
                severity="warning",
                message="Example warning.",
                slice_indices=(2,),
            ),
        )
    )

    json_path, text_path = report.write(tmp_path)

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["passed"] is True
    assert payload["warning_count"] == 1
    assert "Example warning." in text_path.read_text(encoding="utf-8")
