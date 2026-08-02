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
    assert json_path.name == "WENL长卷_导出验证报告.json"
    assert text_path.name == "WENL长卷_导出验证报告.txt"
    assert payload["brand"] == "WENL / 长卷"
    assert payload["passed"] is True
    assert payload["warning_count"] == 1
    report_text = text_path.read_text(encoding="utf-8")
    assert "WENL / 长卷" in report_text
    assert "Example warning." in report_text


def test_grayscale_output_is_validated_without_band_unpack_error(
    tmp_path: Path,
) -> None:
    source_image = Image.new("L", (5, 5), 127)
    composite = CompositeResult(
        image=source_image,
        source="embedded_merged",
        width=5,
        height=5,
        color_mode="GRAYSCALE",
        depth=8,
        pil_mode="L",
        icc_profile=None,
        has_alpha=False,
        is_reliable=True,
    )
    info = slice_info(0, (0, 0, 5, 5))
    mapped = MappedSlice(info, 0, 0, 5, 5)
    output = tmp_path / "gray.png"
    source_image.save(output)
    exported = ExportedSlice(
        info,
        output,
        5,
        5,
        "L",
        output.stat().st_size,
    )

    report = validate_export_outputs(
        [mapped],
        [exported],
        [],
        composite=composite,
        original_size=False,
        expected_format="PNG",
        expected_alpha=False,
    )

    assert "image_reopen_failed" not in {
        item.code for item in report.findings
    }
    assert report.passed
    source_image.close()


def test_post_export_validation_honors_cancellation(
    tmp_path: Path,
) -> None:
    source_image = Image.new("RGB", (5, 5), (1, 2, 3))
    composite = CompositeResult(
        image=source_image,
        source="embedded_merged",
        width=5,
        height=5,
        color_mode="RGB",
        depth=8,
        pil_mode="RGB",
        icc_profile=None,
        has_alpha=False,
        is_reliable=True,
    )
    info = slice_info(0, (0, 0, 5, 5))

    report = validate_export_outputs(
        [MappedSlice(info, 0, 0, 5, 5)],
        [],
        [],
        composite=composite,
        original_size=False,
        cancel_check=lambda: True,
    )

    assert "validation_cancelled" in {
        finding.code for finding in report.findings
    }
    source_image.close()
