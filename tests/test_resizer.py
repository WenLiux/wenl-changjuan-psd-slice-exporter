from __future__ import annotations

from PIL import Image, ImageChops

from app.core.resizer import (
    ResizePlanError,
    build_scale_plan,
    resize_full_composite,
    resize_mapped_slice,
)
from app.models.slice_info import SliceInfo


def vertical_slices(
    width: int,
    boundaries: list[int],
) -> list[SliceInfo]:
    return [
        SliceInfo(
            index=index,
            slice_id=index + 1,
            name=f"slice-{index}",
            left=0,
            top=top,
            right=width,
            bottom=bottom,
            is_automatic=False,
            source_version="V8",
            origin="userGenerated",
        )
        for index, (top, bottom) in enumerate(
            zip(boundaries, boundaries[1:])
        )
    ]


def gradient_image(width: int, height: int) -> Image.Image:
    image = Image.new("RGB", (width, height))
    image.putdata(
        [
            (
                (x * 17 + y * 3) % 256,
                (x * 5 + y * 11) % 256,
                (x * 13 + y * 7) % 256,
            )
            for y in range(height)
            for x in range(width)
        ]
    )
    return image


def test_750px_mapping_has_no_gaps_or_repeated_boundaries() -> None:
    canvas_width = 1440
    canvas_height = 28164
    boundaries = [
        0,
        3024,
        5353,
        7342,
        9332,
        11644,
        13674,
        15746,
        17300,
        19806,
        21663,
        23580,
        25257,
        26812,
        28164,
    ]
    plan = build_scale_plan(
        canvas_width=canvas_width,
        canvas_height=canvas_height,
        slices=vertical_slices(canvas_width, boundaries),
        target_width=750,
        allow_upscale=True,
    )

    assert plan.output_width == 750
    assert plan.output_height == round(canvas_height * 750 / canvas_width)
    assert all(item.width == 750 for item in plan.mapped_slices)
    assert plan.mapped_slices[0].top == 0
    assert plan.mapped_slices[-1].bottom == plan.output_height
    assert all(
        current.bottom == following.top
        for current, following in zip(
            plan.mapped_slices,
            plan.mapped_slices[1:],
        )
    )
    assert sum(item.height for item in plan.mapped_slices) == plan.output_height


def test_upscale_can_be_blocked() -> None:
    try:
        build_scale_plan(
            canvas_width=100,
            canvas_height=100,
            slices=vertical_slices(100, [0, 100]),
            target_width=200,
            allow_upscale=False,
        )
    except ResizePlanError as error:
        assert "upscaling is disabled" in str(error)
    else:
        raise AssertionError("Expected ResizePlanError")


def test_per_slice_resize_uses_global_pixel_grid() -> None:
    source = gradient_image(37, 53)
    plan = build_scale_plan(
        canvas_width=37,
        canvas_height=53,
        slices=vertical_slices(37, [0, 17, 31, 53]),
        target_width=23,
        allow_upscale=True,
    )
    full = resize_full_composite(source, plan)
    stitched = Image.new(full.mode, full.size)

    for mapped_slice in plan.mapped_slices:
        tile = resize_mapped_slice(
            source,
            mapped_slice,
            plan,
            edge_padding=8,
        )
        stitched.paste(tile, (mapped_slice.left, mapped_slice.top))
        tile.close()

    difference = ImageChops.difference(full, stitched)
    assert difference.getbbox() is None
    difference.close()
    stitched.close()
    full.close()
    source.close()
