from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageCms

from app.core.image_encoder import (
    ImageEncodingError,
    build_image_encoding_plan,
)
from app.models.composite_result import CompositeResult
from app.models.export_result import ExportOptions
from app.models.slice_info import SliceInfo, SliceParseResult
from app.services.export_service import (
    ExportPreflightError,
    export_prepared_original_size,
)
from app.utils.image_modes import image_has_alpha


def prepared_document(
    source_path: Path,
    *,
    color_mode: str = "RGB",
    depth: int = 8,
    icc_profile: bytes | None = None,
) -> tuple[SliceParseResult, CompositeResult]:
    source_path.write_bytes(b"fixture")
    slice_info = SliceInfo(
        index=0,
        slice_id=1,
        name="all",
        left=0,
        top=0,
        right=8,
        bottom=8,
        is_automatic=False,
        source_version="V8",
        origin="userGenerated",
    )
    slices = SliceParseResult(
        source_version="V8",
        all_slices=(slice_info,),
        exportable_slices=(slice_info,),
        excluded_slices=(),
        issues=(),
    )
    composite = CompositeResult(
        image=Image.new("RGBA", (8, 8), (10, 20, 30, 128)),
        source="embedded_merged",
        width=8,
        height=8,
        color_mode=color_mode,
        depth=depth,
        pil_mode="RGBA",
        icc_profile=icc_profile,
        has_alpha=True,
        is_reliable=True,
    )
    return slices, composite


def srgb_profile_bytes() -> bytes:
    return ImageCms.ImageCmsProfile(
        ImageCms.createProfile("sRGB")
    ).tobytes()


def test_format_defaults_select_safe_color_policies(tmp_path: Path) -> None:
    slices, composite = prepared_document(tmp_path / "defaults.psd")
    png_plan = build_image_encoding_plan(composite, ExportOptions())
    jpeg_plan = build_image_encoding_plan(
        composite,
        ExportOptions(output_format="jpeg"),
    )

    assert png_plan.color_policy == "preserve"
    assert png_plan.output_icc_profile is None
    assert jpeg_plan.color_policy == "srgb"
    assert jpeg_plan.output_icc_profile
    composite.image.close()


@pytest.mark.parametrize("quality", [0, 101])
def test_jpeg_quality_must_be_between_one_and_one_hundred(
    quality: int,
) -> None:
    with pytest.raises(ValueError, match="JPEG quality"):
        ExportOptions(output_format="jpeg", jpeg_quality=quality)


def test_png_preserves_alpha_and_original_profile(tmp_path: Path) -> None:
    profile = srgb_profile_bytes()
    slices, composite = prepared_document(
        tmp_path / "alpha.psd",
        icc_profile=profile,
    )

    result = export_prepared_original_size(
        tmp_path / "alpha.psd",
        slices,
        composite,
        ExportOptions(output_parent=tmp_path),
    )

    assert result.success
    assert result.output_format == "png"
    assert result.color_policy == "preserve"
    assert result.exported_slices[0].output_path.suffix == ".png"
    with Image.open(result.exported_slices[0].output_path) as output:
        output.load()
        assert output.mode == "RGBA"
        assert output.getpixel((0, 0)) == (10, 20, 30, 128)
        assert output.info["icc_profile"] == profile
    composite.image.close()


def test_jpeg_flattens_alpha_on_selected_background_and_embeds_srgb(
    tmp_path: Path,
) -> None:
    slices, composite = prepared_document(tmp_path / "photo.psd")

    result = export_prepared_original_size(
        tmp_path / "photo.psd",
        slices,
        composite,
        ExportOptions(
            output_parent=tmp_path,
            output_format="jpeg",
            jpeg_quality=100,
            jpeg_background=(210, 110, 60),
        ),
    )

    assert result.success
    assert result.output_format == "jpeg"
    assert result.color_policy == "srgb"
    output_path = result.exported_slices[0].output_path
    assert output_path.suffix == ".jpg"
    with Image.open(output_path) as output:
        output.load()
        assert output.format == "JPEG"
        assert output.mode == "RGB"
        assert output.info["icc_profile"]
        expected = (110, 65, 45)
        assert all(
            abs(actual - target) <= 2
            for actual, target in zip(output.getpixel((0, 0)), expected)
        )
    assert "pixel_mismatch" not in {
        finding.code for finding in result.validation_report.findings
    }
    composite.image.close()


def test_unsupported_color_or_depth_requires_explicit_confirmation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "cmyk.psd"
    slices, composite = prepared_document(
        source,
        color_mode="CMYK",
        depth=16,
    )

    with pytest.raises(
        ExportPreflightError,
        match="CMYK color, 16-bit depth",
    ):
        export_prepared_original_size(
            source,
            slices,
            composite,
            ExportOptions(output_parent=tmp_path),
        )
    assert not (tmp_path / "cmyk_slices_original").exists()
    composite.image.close()


def test_explicit_mode_conversion_permission_allows_export(
    tmp_path: Path,
) -> None:
    source = tmp_path / "confirmed.psd"
    slices, composite = prepared_document(
        source,
        color_mode="RGB",
        depth=16,
    )

    result = export_prepared_original_size(
        source,
        slices,
        composite,
        ExportOptions(
            output_parent=tmp_path,
            allow_mode_conversion=True,
        ),
    )

    assert result.success
    composite.image.close()


def test_non_rgb_conversion_requires_a_compatible_icc_profile(
    tmp_path: Path,
) -> None:
    source = tmp_path / "managed-cmyk.psd"
    slices, composite = prepared_document(
        source,
        color_mode="CMYK",
    )
    composite.image.close()
    composite.image = Image.new("CMYK", (8, 8), (0, 0, 0, 0))
    composite.pil_mode = "CMYK"
    composite.has_alpha = False

    with pytest.raises(
        ExportPreflightError,
        match="requires a compatible embedded ICC profile",
    ):
        export_prepared_original_size(
            source,
            slices,
            composite,
            ExportOptions(
                output_parent=tmp_path,
                color_policy="srgb",
                allow_mode_conversion=True,
            ),
        )
    assert not (tmp_path / "managed-cmyk_slices_original").exists()
    composite.image.close()


def test_lab_a_band_is_not_treated_as_transparency() -> None:
    image = Image.new("LAB", (2, 2), (50, 128, 128))
    assert image.getbands() == ("L", "A", "B")
    assert not image_has_alpha(image)
    image.close()


def test_invalid_embedded_profile_blocks_srgb_conversion(
    tmp_path: Path,
) -> None:
    _, composite = prepared_document(
        tmp_path / "invalid-profile.psd",
        icc_profile=b"not-an-icc-profile",
    )
    with pytest.raises(ImageEncodingError, match="cannot be opened"):
        build_image_encoding_plan(
            composite,
            ExportOptions(output_format="jpeg"),
        )
    composite.image.close()
