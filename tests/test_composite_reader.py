from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from psd_tools import PSDImage
from psd_tools.constants import Resource

from app.core.composite_reader import read_embedded_composite


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads(
    (PROJECT_ROOT / "tests" / "fixtures" / "baseline_manifest.json").read_text(
        encoding="utf-8"
    )
)


class FakeResources:
    def __init__(
        self,
        *,
        version_info: object | None,
        icc_profile: bytes | None = None,
    ) -> None:
        self.version_info = version_info
        self.icc_profile = icc_profile

    def get_data(self, resource: Resource) -> object | None:
        if resource == Resource.VERSION_INFO:
            return self.version_info
        if resource == Resource.ICC_PROFILE:
            return self.icc_profile
        return None


class FakePSD:
    def __init__(
        self,
        *,
        image: Image.Image | None,
        has_preview: bool = True,
        has_composite: bool | None = True,
        icc_profile: bytes | None = None,
        width: int = 10,
        height: int = 20,
    ) -> None:
        version_info = (
            None
            if has_composite is None
            else SimpleNamespace(has_composite=has_composite)
        )
        self.image_resources = FakeResources(
            version_info=version_info,
            icc_profile=icc_profile,
        )
        self.width = width
        self.height = height
        self.depth = 8
        self.color_mode = SimpleNamespace(name="RGB")
        self._image = image
        self._has_preview = has_preview
        self.apply_icc_calls: list[bool] = []
        self.composite_called = False

    def has_preview(self) -> bool:
        return self._has_preview

    def topil(self, *, apply_icc: bool) -> Image.Image | None:
        self.apply_icc_calls.append(apply_icc)
        return self._image

    def composite(self) -> Image.Image:
        self.composite_called = True
        raise AssertionError("Layer compositing must never be called")


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


def image_pixel_sha256(image: Image.Image) -> str:
    image.load()
    digest = hashlib.sha256()
    digest.update(image.mode.encode("ascii"))
    digest.update(f"{image.width}x{image.height}".encode("ascii"))
    digest.update(image.tobytes())
    return digest.hexdigest()


@pytest.mark.parametrize("sample_name", ["psd_v8", "psb_v6"])
def test_real_fixture_uses_reliable_embedded_merged_data(
    sample_name: str,
) -> None:
    sample = MANIFEST[sample_name]
    psd = PSDImage.open(fixture_path(sample_name))

    result = read_embedded_composite(psd)

    assert result.is_available
    assert result.source == "embedded_merged"
    assert result.is_reliable
    assert not result.requires_photoshop
    assert [result.width, result.height] == sample["canvas"]
    assert result.color_mode == "RGB"
    assert result.depth == 8
    assert result.pil_mode == "RGBA"
    assert result.has_alpha
    assert result.icc_profile is None
    assert result.warning is None
    assert result.error is None

    first_output = sample["outputs"][0]
    _, width, height, _, expected_hash = first_output
    assert result.image is not None
    first_slice = result.image.crop((0, 0, width, height))
    assert image_pixel_sha256(first_slice) == expected_hash
    first_slice.close()
    result.image.close()


def test_reader_preserves_icc_bytes_and_never_composites_layers() -> None:
    image = Image.new("RGBA", (10, 20), (1, 2, 3, 4))
    psd = FakePSD(image=image, icc_profile=b"fake-icc")

    result = read_embedded_composite(psd)

    assert result.image is image
    assert result.icc_profile == b"fake-icc"
    assert psd.apply_icc_calls == [False]
    assert not psd.composite_called
    assert result.is_reliable


def test_explicit_missing_composite_does_not_attempt_decode() -> None:
    psd = FakePSD(
        image=Image.new("RGB", (10, 20)),
        has_composite=False,
    )

    result = read_embedded_composite(psd)

    assert result.image is None
    assert result.source == "missing"
    assert result.requires_photoshop
    assert "Maximize Compatibility" in (result.error or "")
    assert psd.apply_icc_calls == []
    assert not psd.composite_called


def test_missing_version_info_is_decoded_but_marked_unverified() -> None:
    image = Image.new("RGB", (10, 20))
    psd = FakePSD(image=image, has_composite=None)

    result = read_embedded_composite(psd)

    assert result.image is image
    assert result.source == "embedded_merged_unverified"
    assert not result.is_reliable
    assert result.warning
    assert not result.requires_photoshop


def test_size_mismatch_is_rejected() -> None:
    psd = FakePSD(
        image=Image.new("RGB", (9, 20)),
        width=10,
        height=20,
    )

    result = read_embedded_composite(psd)

    assert result.image is None
    assert result.source == "invalid"
    assert "dimensions do not match" in (result.error or "")
    assert result.requires_photoshop


def test_decode_failure_is_returned_as_user_readable_error() -> None:
    class BrokenPSD(FakePSD):
        def topil(self, *, apply_icc: bool) -> Image.Image | None:
            raise ValueError("corrupt merged channels")

    result = read_embedded_composite(BrokenPSD(image=None))

    assert result.image is None
    assert result.source == "invalid"
    assert "corrupt merged channels" in (result.error or "")
    assert result.requires_photoshop


def test_lab_a_band_is_not_reported_as_alpha(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.composite_reader.has_transparency",
        lambda psd: False,
    )
    psd = FakePSD(image=Image.new("LAB", (10, 20)))

    result = read_embedded_composite(psd)

    assert result.image is not None
    assert not result.has_alpha
    result.image.close()


def test_unrepresentable_non_rgb_transparency_requires_photoshop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.core.composite_reader.has_transparency",
        lambda psd: True,
    )
    psd = FakePSD(image=Image.new("CMYK", (10, 20)))

    result = read_embedded_composite(psd)

    assert result.image is None
    assert result.requires_photoshop
    assert "transparency" in (result.error or "")
