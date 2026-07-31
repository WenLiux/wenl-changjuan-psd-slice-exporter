from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from psd_tools import PSDImage
from psd_tools.constants import Resource


def get_value(mapping, key: str) -> int:
    for candidate in (key, key.encode("ascii")):
        try:
            return int(mapping[candidate])
        except (KeyError, TypeError):
            pass
    raise KeyError(key)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export PSD user slices at their original pixel dimensions."
    )
    parser.add_argument("psd", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    psd = PSDImage.open(args.psd)
    slice_resource = psd.image_resources.get_data(Resource.SLICES)
    if slice_resource is None:
        raise RuntimeError("The PSD does not contain a Slices image resource.")

    slices: list[tuple[int, int, int, int, int]] = []
    slice_data = slice_resource.data
    if slice_resource.version == 6:
        # Version 6 slice resources store each bbox as
        # [left, top, right, bottom].
        for record in slice_data.items:
            left, top, right, bottom = map(int, record.bbox)
            slices.append((top, left, bottom, right, int(record.slice_id)))
    else:
        # Version 7/8 slice resources use Photoshop descriptors.
        for record in slice_data[b"slices"]:
            bounds = record[b"bounds"]
            left = get_value(bounds, "Left")
            top = get_value(bounds, "Top ")
            right = get_value(bounds, "Rght")
            bottom = get_value(bounds, "Btom")
            slice_id = int(record[b"sliceID"])
            slices.append((top, left, bottom, right, slice_id))

    # Photoshop can store an automatic full-canvas slice alongside the user's
    # non-overlapping content slices. Omit that redundant item when there are
    # other slices to export.
    if len(slices) > 1:
        slices = [
            item
            for item in slices
            if item[:4] != (0, 0, psd.height, psd.width)
        ]

    slices.sort()
    args.output.mkdir(parents=True, exist_ok=True)

    # PSDImage.topil() uses Photoshop's embedded merged composite, which most
    # closely matches what Photoshop displays while preserving original pixels.
    composite = psd.topil()
    if composite is None:
        raise RuntimeError("The PSD has no embedded merged composite.")

    exported: list[Path] = []
    for index, (top, left, bottom, right, slice_id) in enumerate(slices, start=1):
        if not (0 <= left < right <= psd.width and 0 <= top < bottom <= psd.height):
            raise RuntimeError(
                f"Slice {slice_id} is outside the canvas: "
                f"({left}, {top}, {right}, {bottom})"
            )
        crop = composite.crop((left, top, right, bottom))
        output_file = args.output / f"slice_{index:02d}_{crop.width}x{crop.height}.png"
        crop.save(output_file, format="PNG", compress_level=6)
        exported.append(output_file)
        print(
            f"{output_file.name}: {crop.width}x{crop.height} "
            f"from ({left}, {top})-({right}, {bottom})"
        )

    archive = shutil.make_archive(str(args.output), "zip", root_dir=args.output)
    print(f"Exported {len(exported)} slices to: {args.output}")
    print(f"ZIP: {archive}")


if __name__ == "__main__":
    main()
