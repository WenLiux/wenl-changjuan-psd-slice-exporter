from __future__ import annotations

from PIL import Image


ALPHA_MODES = frozenset({"LA", "La", "PA", "RGBA", "RGBa"})


def mode_has_alpha(mode: str) -> bool:
    """Return whether a Pillow mode has a real opacity channel."""

    return mode in ALPHA_MODES


def image_has_alpha(image: Image.Image) -> bool:
    """Detect opacity without confusing the A color channel in LAB."""

    if mode_has_alpha(image.mode):
        return True
    return image.mode == "P" and "transparency" in image.info
