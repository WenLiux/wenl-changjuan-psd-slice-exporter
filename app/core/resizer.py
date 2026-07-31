from __future__ import annotations

from collections.abc import Sequence

from PIL import Image

from app.models.scale_plan import MappedSlice, ScalePlan
from app.models.slice_info import SliceInfo


class ResizePlanError(ValueError):
    """Raised when a requested global resize cannot produce valid slices."""


def map_coordinate(value: int, scale: float) -> int:
    """Map one source boundary with the global rounding rule."""

    return round(value * scale)


def build_scale_plan(
    *,
    canvas_width: int,
    canvas_height: int,
    slices: Sequence[SliceInfo],
    target_width: int | None,
    allow_upscale: bool,
) -> ScalePlan:
    if canvas_width <= 0 or canvas_height <= 0:
        raise ResizePlanError("Canvas dimensions must be positive.")

    output_width = canvas_width if target_width is None else int(target_width)
    if output_width <= 0:
        raise ResizePlanError("Target width must be a positive integer.")
    if output_width > canvas_width and not allow_upscale:
        raise ResizePlanError(
            f"Target width {output_width}px would enlarge the "
            f"{canvas_width}px source while upscaling is disabled."
        )

    scale = output_width / canvas_width
    output_height = map_coordinate(canvas_height, scale)
    mapped: list[MappedSlice] = []
    for item in slices:
        mapped_item = MappedSlice(
            slice_info=item,
            left=map_coordinate(item.left, scale),
            top=map_coordinate(item.top, scale),
            right=map_coordinate(item.right, scale),
            bottom=map_coordinate(item.bottom, scale),
        )
        if mapped_item.width <= 0 or mapped_item.height <= 0:
            raise ResizePlanError(
                f"Slice {item.index} becomes {mapped_item.width} x "
                f"{mapped_item.height}px at target width {output_width}px."
            )
        mapped.append(mapped_item)

    return ScalePlan(
        source_width=canvas_width,
        source_height=canvas_height,
        output_width=output_width,
        output_height=output_height,
        scale=scale,
        mapped_slices=tuple(mapped),
    )


def resize_full_composite(
    image: Image.Image,
    plan: ScalePlan,
) -> Image.Image:
    """Resize the complete composite once using the global scale plan."""

    if plan.is_original_size:
        return image.copy()
    return image.resize(
        (plan.output_width, plan.output_height),
        resample=Image.Resampling.LANCZOS,
    )


def resize_mapped_slice(
    image: Image.Image,
    mapped_slice: MappedSlice,
    plan: ScalePlan,
    *,
    edge_padding: int = 8,
) -> Image.Image:
    """Render one globally aligned slice without a full resized canvas."""

    if plan.is_original_size:
        return image.crop(mapped_slice.bounds)

    expanded_left = max(0, mapped_slice.left - edge_padding)
    expanded_top = max(0, mapped_slice.top - edge_padding)
    expanded_right = min(
        plan.output_width,
        mapped_slice.right + edge_padding,
    )
    expanded_bottom = min(
        plan.output_height,
        mapped_slice.bottom + edge_padding,
    )
    expanded_width = expanded_right - expanded_left
    expanded_height = expanded_bottom - expanded_top
    source_per_output_x = plan.source_width / plan.output_width
    source_per_output_y = plan.source_height / plan.output_height
    source_box = (
        expanded_left * source_per_output_x,
        expanded_top * source_per_output_y,
        expanded_right * source_per_output_x,
        expanded_bottom * source_per_output_y,
    )

    expanded = image.resize(
        (expanded_width, expanded_height),
        resample=Image.Resampling.LANCZOS,
        box=source_box,
    )
    try:
        return expanded.crop(
            (
                mapped_slice.left - expanded_left,
                mapped_slice.top - expanded_top,
                mapped_slice.right - expanded_left,
                mapped_slice.bottom - expanded_top,
            )
        )
    finally:
        expanded.close()
