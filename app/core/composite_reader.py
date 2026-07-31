from __future__ import annotations

from pathlib import Path
from typing import Any

from psd_tools import PSDImage
from psd_tools.api.utils import has_transparency
from psd_tools.constants import Resource

from app.models.composite_result import CompositeResult, CompositeSource
from app.utils.image_modes import image_has_alpha


class CompositeReaderError(RuntimeError):
    """Base class for user-facing composite reader errors."""


class CompositeOpenError(CompositeReaderError):
    """Raised when a PSD/PSB cannot be opened."""


def _color_mode_name(psd: Any) -> str:
    color_mode = getattr(psd, "color_mode", None)
    name = getattr(color_mode, "name", None)
    if name:
        return str(name)
    return str(color_mode) if color_mode is not None else "UNKNOWN"


def _image_resource(psd: Any, resource: Resource) -> Any | None:
    try:
        return psd.image_resources.get_data(resource)
    except (KeyError, TypeError):
        return None


def _has_document_transparency(psd: Any, image: Any) -> bool:
    try:
        return bool(has_transparency(psd))
    except (AttributeError, KeyError, TypeError):
        # Lightweight test doubles and older compatible readers may not expose
        # the low-level channel metadata used by psd-tools.
        return image_has_alpha(image)


def _unavailable_result(
    psd: Any,
    *,
    source: CompositeSource,
    icc_profile: bytes | None,
    error: str,
    warning: str | None = None,
) -> CompositeResult:
    return CompositeResult(
        image=None,
        source=source,
        width=int(psd.width),
        height=int(psd.height),
        color_mode=_color_mode_name(psd),
        depth=int(psd.depth),
        pil_mode=None,
        icc_profile=icc_profile,
        has_alpha=False,
        is_reliable=False,
        warning=warning,
        error=error,
    )


def read_embedded_composite(psd: Any) -> CompositeResult:
    """Read only Photoshop-saved merged data, never a layer re-render."""

    icc_profile = _image_resource(psd, Resource.ICC_PROFILE)
    version_info = _image_resource(psd, Resource.VERSION_INFO)
    explicit_composite = (
        bool(version_info.has_composite) if version_info is not None else None
    )

    if explicit_composite is False:
        return _unavailable_result(
            psd,
            source="missing",
            icc_profile=icc_profile,
            error=(
                "The PSD/PSB does not contain a complete Photoshop-saved "
                "composite. Re-save with Maximize Compatibility enabled or "
                "use Photoshop high-fidelity mode."
            ),
        )

    try:
        has_preview = bool(psd.has_preview())
    except Exception as error:
        return _unavailable_result(
            psd,
            source="invalid",
            icc_profile=icc_profile,
            error=f"Unable to inspect the embedded composite: {error}",
        )

    if not has_preview:
        return _unavailable_result(
            psd,
            source="missing",
            icc_profile=icc_profile,
            error=(
                "No embedded Photoshop composite is available. Re-save with "
                "Maximize Compatibility enabled or use Photoshop "
                "high-fidelity mode."
            ),
        )

    try:
        # apply_icc=False preserves the stored channel values. Color conversion
        # is an explicit later export-stage decision.
        image = psd.topil(apply_icc=False)
        if image is not None:
            image.load()
    except Exception as error:
        return _unavailable_result(
            psd,
            source="invalid",
            icc_profile=icc_profile,
            error=f"Failed to decode the embedded Photoshop composite: {error}",
        )

    if image is None:
        return _unavailable_result(
            psd,
            source="invalid",
            icc_profile=icc_profile,
            error="The embedded Photoshop composite could not be decoded.",
        )

    expected_size = (int(psd.width), int(psd.height))
    if image.size != expected_size:
        actual_width, actual_height = image.size
        image.close()
        return _unavailable_result(
            psd,
            source="invalid",
            icc_profile=icc_profile,
            error=(
                "The embedded composite dimensions do not match the document "
                f"canvas: expected {expected_size[0]} x {expected_size[1]}, "
                f"got {actual_width} x {actual_height}."
            ),
        )

    document_has_transparency = _has_document_transparency(psd, image)
    decoded_has_alpha = image_has_alpha(image)
    if document_has_transparency and not decoded_has_alpha:
        decoded_mode = image.mode
        image.close()
        return _unavailable_result(
            psd,
            source="invalid",
            icc_profile=icc_profile,
            error=(
                "The embedded composite contains transparency that cannot be "
                f"represented in decoded {decoded_mode} mode without losing "
                "data. Use Photoshop high-fidelity mode."
            ),
        )

    is_reliable = explicit_composite is True
    warning = None
    source: CompositeSource = "embedded_merged"
    if explicit_composite is None:
        source = "embedded_merged_unverified"
        warning = (
            "The PSD/PSB has no VERSION_INFO composite flag. Merged image data "
            "was decoded, but its completeness cannot be confirmed."
        )

    return CompositeResult(
        image=image,
        source=source,
        width=expected_size[0],
        height=expected_size[1],
        color_mode=_color_mode_name(psd),
        depth=int(psd.depth),
        pil_mode=image.mode,
        icc_profile=icc_profile,
        has_alpha=document_has_transparency,
        is_reliable=is_reliable,
        warning=warning,
    )


def read_document_composite(path: str | Path) -> CompositeResult:
    """Open a PSD/PSB and read its embedded merged composite."""

    source_path = Path(path)
    try:
        psd = PSDImage.open(source_path)
    except Exception as error:
        raise CompositeOpenError(
            f"Unable to open PSD/PSB file '{source_path.name}': {error}"
        ) from error
    return read_embedded_composite(psd)
