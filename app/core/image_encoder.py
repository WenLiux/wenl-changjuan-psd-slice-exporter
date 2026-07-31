from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from typing import Literal

from PIL import Image, ImageCms

from app.models.composite_result import CompositeResult
from app.models.export_result import ColorPolicy, ExportOptions, OutputFormat
from app.utils.image_modes import image_has_alpha


ResolvedColorPolicy = Literal["preserve", "srgb"]
PNG_MODES = frozenset(
    {"1", "L", "LA", "P", "RGB", "RGBA", "I", "I;16"}
)


class ImageEncodingError(RuntimeError):
    """Raised when requested output would require an unsafe conversion."""


@dataclass(frozen=True, slots=True)
class ImageEncodingPlan:
    output_format: OutputFormat
    extension: str
    color_policy: ResolvedColorPolicy
    output_icc_profile: bytes | None
    source_icc_profile: bytes | None
    jpeg_quality: int
    jpeg_background: tuple[int, int, int]
    needs_mode_conversion: bool
    source_has_alpha: bool
    expected_alpha: bool
    color_transform: ImageCms.ImageCmsTransform | None

    @property
    def exact_pixels_preserved(self) -> bool:
        return (
            self.output_format == "png"
            and self.color_policy == "preserve"
            and not self.needs_mode_conversion
            and self.color_transform is None
        )


@lru_cache(maxsize=1)
def _srgb_profile() -> ImageCms.ImageCmsProfile:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB"))


@lru_cache(maxsize=1)
def _srgb_profile_bytes() -> bytes:
    return _srgb_profile().tobytes()


def _open_profile(profile_bytes: bytes) -> ImageCms.ImageCmsProfile:
    try:
        return ImageCms.ImageCmsProfile(BytesIO(profile_bytes))
    except Exception as error:
        raise ImageEncodingError(
            f"The document ICC profile cannot be opened: {error}"
        ) from error


def _resolved_color_policy(
    output_format: OutputFormat,
    color_policy: ColorPolicy,
) -> ResolvedColorPolicy:
    if color_policy != "auto":
        return color_policy
    return "preserve" if output_format == "png" else "srgb"


def build_image_encoding_plan(
    composite: CompositeResult,
    options: ExportOptions,
) -> ImageEncodingPlan:
    """Validate color/mode choices before any output directory is created."""

    output_format = options.output_format
    color_policy = _resolved_color_policy(
        output_format,
        options.color_policy,
    )
    if composite.image is None:
        raise ImageEncodingError("No composite image is available to encode.")
    pil_mode = composite.image.mode
    if (
        composite.pil_mode is not None
        and composite.pil_mode != pil_mode
    ):
        raise ImageEncodingError(
            "The decoded composite mode changed unexpectedly from "
            f"{composite.pil_mode} to {pil_mode}. Use Photoshop "
            "high-fidelity mode."
        )
    actual_has_alpha = image_has_alpha(composite.image)
    if composite.has_alpha != actual_has_alpha:
        raise ImageEncodingError(
            "The decoded composite transparency metadata does not match its "
            f"{pil_mode} pixel mode. Use Photoshop high-fidelity mode."
        )
    source_mode = composite.color_mode.upper()
    safely_supported = (
        composite.depth == 8
        and source_mode == "RGB"
        and pil_mode in {"RGB", "RGBA"}
    )
    if not safely_supported and not options.allow_mode_conversion:
        raise ImageEncodingError(
            "The document uses "
            f"{composite.color_mode} color, {composite.depth}-bit depth, "
            f"decoded as {pil_mode}. Export would require a color or bit-depth "
            "conversion. Confirm mode conversion explicitly or use Photoshop "
            "high-fidelity mode."
        )

    source_icc_profile = composite.icc_profile
    color_transform: ImageCms.ImageCmsTransform | None = None
    if color_policy == "srgb":
        if source_icc_profile:
            source_profile = _open_profile(source_icc_profile)
            output_mode = "RGBA" if actual_has_alpha else "RGB"
            try:
                color_transform = (
                    ImageCms.buildTransformFromOpenProfiles(
                        source_profile,
                        _srgb_profile(),
                        pil_mode,
                        output_mode,
                        renderingIntent=(
                            ImageCms.Intent.RELATIVE_COLORIMETRIC
                        ),
                    )
                )
            except Exception as error:
                raise ImageEncodingError(
                    "The document ICC profile is not compatible with decoded "
                    f"{pil_mode} pixels, so an sRGB transform cannot be built: "
                    f"{error}"
                ) from error
        elif source_mode != "RGB" or pil_mode not in {"RGB", "RGBA"}:
            raise ImageEncodingError(
                "A managed sRGB conversion from "
                f"{composite.color_mode}/{pil_mode} requires a compatible "
                "embedded ICC profile. Use Photoshop high-fidelity mode."
            )
    elif output_format == "png":
        if pil_mode not in PNG_MODES:
            raise ImageEncodingError(
                f"PNG cannot preserve decoded {pil_mode} pixels and their "
                "original ICC profile. Select sRGB conversion with a "
                "compatible source profile or use Photoshop high-fidelity "
                "mode."
            )
    elif pil_mode not in {"RGB", "RGBA"}:
        raise ImageEncodingError(
            f"JPEG requires RGB pixels, so decoded {pil_mode} data cannot "
            "preserve its original ICC profile. Select sRGB conversion with "
            "a compatible source profile or use Photoshop high-fidelity mode."
        )

    if (
        output_format == "jpeg"
        and color_policy == "preserve"
        and actual_has_alpha
    ):
        raise ImageEncodingError(
            "A JPEG transparency background is defined in sRGB. Select the "
            "sRGB color policy before flattening alpha, or use PNG."
        )

    if color_policy == "srgb":
        output_icc_profile = _srgb_profile_bytes()
    else:
        output_icc_profile = source_icc_profile

    return ImageEncodingPlan(
        output_format=output_format,
        extension=".png" if output_format == "png" else ".jpg",
        color_policy=color_policy,
        output_icc_profile=output_icc_profile,
        source_icc_profile=source_icc_profile,
        jpeg_quality=options.jpeg_quality,
        jpeg_background=options.jpeg_background,
        needs_mode_conversion=not safely_supported,
        source_has_alpha=actual_has_alpha,
        expected_alpha=(
            output_format == "png" and actual_has_alpha
        ),
        color_transform=color_transform,
    )


def _convert_to_srgb(
    image: Image.Image,
    transform: ImageCms.ImageCmsTransform | None,
) -> Image.Image:
    if transform is None:
        # Untagged 8-bit RGB documents are treated as sRGB. This changes only
        # the profile metadata; channel values remain untouched.
        return image.copy()

    try:
        return ImageCms.applyTransform(image, transform)
    except Exception as error:
        raise ImageEncodingError(
            f"Unable to convert the slice to sRGB: {error}"
        ) from error


def _flatten_for_jpeg(
    image: Image.Image,
    background: tuple[int, int, int],
) -> Image.Image:
    if not image_has_alpha(image):
        return image.convert("RGB")
    rgba = image if image.mode == "RGBA" else image.convert("RGBA")
    background_image = Image.new("RGBA", image.size, (*background, 255))
    try:
        flattened = Image.alpha_composite(background_image, rgba)
        return flattened.convert("RGB")
    finally:
        background_image.close()
        if rgba is not image:
            rgba.close()


def prepare_image_for_encoding(
    image: Image.Image,
    plan: ImageEncodingPlan,
) -> Image.Image:
    """Return an owned image ready for the encoder selected in the plan."""

    if plan.color_policy == "srgb":
        prepared = _convert_to_srgb(image, plan.color_transform)
    else:
        prepared = image.copy()

    if plan.output_format == "png":
        return prepared

    try:
        return _flatten_for_jpeg(prepared, plan.jpeg_background)
    finally:
        prepared.close()


def save_options_for_plan(plan: ImageEncodingPlan) -> dict[str, object]:
    if plan.output_format == "png":
        options: dict[str, object] = {"format": "PNG"}
    else:
        options = {
            "format": "JPEG",
            "quality": plan.jpeg_quality,
            "subsampling": 0,
        }
    if plan.output_icc_profile:
        options["icc_profile"] = plan.output_icc_profile
    return options
