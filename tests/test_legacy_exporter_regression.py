from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from PIL import Image
from psd_tools import PSDImage
from psd_tools.constants import Resource


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPORTER = PROJECT_ROOT / "legacy" / "export_psd_slices_1440.py"
MANIFEST_PATH = PROJECT_ROOT / "tests" / "fixtures" / "baseline_manifest.json"
MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def image_pixel_sha256(path: Path) -> str:
    with Image.open(path) as image:
        image.load()
        digest = hashlib.sha256()
        digest.update(image.mode.encode("ascii"))
        digest.update(f"{image.width}x{image.height}".encode("ascii"))
        digest.update(image.tobytes())
        return digest.hexdigest()


def fixture_path(sample: dict[str, object]) -> Path:
    environment_variable = str(sample["environment_variable"])
    value = os.environ.get(environment_variable)
    if not value:
        pytest.skip(f"{environment_variable} is not set")
    path = Path(value)
    if not path.is_file():
        pytest.fail(f"{environment_variable} does not point to a file: {path}")
    return path


@pytest.mark.parametrize("sample_name", ["psd_v8", "psb_v6"])
def test_legacy_export_matches_verified_baseline(
    sample_name: str, tmp_path: Path
) -> None:
    sample = MANIFEST[sample_name]
    source = fixture_path(sample)
    source_stat_before = source.stat()

    assert source.name == sample["file_name"]
    assert source_stat_before.st_size == sample["source_size"]
    assert file_sha256(source) == sample["source_sha256"]

    psd = PSDImage.open(source)
    assert [psd.width, psd.height] == sample["canvas"]
    slices = psd.image_resources.get_data(Resource.SLICES)
    assert slices is not None
    assert slices.version == sample["slice_resource_version"]
    assert psd.has_preview()

    output = tmp_path / sample_name
    result = subprocess.run(
        [sys.executable, str(EXPORTER), str(source), str(output)],
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    expected_outputs = sample["outputs"]
    actual_files = sorted(output.glob("*.png"))
    assert [path.name for path in actual_files] == [
        record[0] for record in expected_outputs
    ]

    for path, expected in zip(actual_files, expected_outputs, strict=True):
        name, width, height, mode, pixel_sha256 = expected
        assert path.name == name
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            assert image.size == (width, height)
            assert image.mode == mode
        assert image_pixel_sha256(path) == pixel_sha256

    archive = output.with_suffix(".zip")
    assert archive.is_file()
    with zipfile.ZipFile(archive) as zip_file:
        assert sorted(zip_file.namelist()) == sorted(
            record[0] for record in expected_outputs
        )
        assert zip_file.testzip() is None

    source_stat_after = source.stat()
    assert source_stat_after.st_size == source_stat_before.st_size
    assert source_stat_after.st_mtime_ns == source_stat_before.st_mtime_ns
    assert file_sha256(source) == sample["source_sha256"]
