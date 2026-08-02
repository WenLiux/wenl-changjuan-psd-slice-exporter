from __future__ import annotations

from app.ui.components import _glass_surface_image, make_ambient_background
from app.ui.theme import THEME


def test_ambient_background_is_subtle_and_non_uniform() -> None:
    image = make_ambient_background(320, 200)
    try:
        assert image.size == (320, 200)
        assert image.mode == "RGBA"
        assert image.getpixel((10, 10)) != image.getpixel((310, 190))
        alpha_values = image.getchannel("A").getextrema()
        assert alpha_values == (255, 255)
    finally:
        image.close()


def test_glass_surface_keeps_rounded_transparent_corners() -> None:
    image = _glass_surface_image(
        240,
        160,
        corner_radius=20,
        emphasized=True,
    )
    try:
        assert image.getpixel((0, 0))[3] == 0
        assert image.getpixel((120, 80))[3] == 255
        assert image.getpixel((120, 8)) != image.getpixel((120, 150))
    finally:
        image.close()


def test_theme_uses_low_contrast_cards_and_reserved_accents() -> None:
    assert THEME.bg_window != THEME.bg_card
    assert THEME.bg_card != THEME.bg_card_secondary
    assert THEME.accent_primary != THEME.bg_selected
    assert THEME.border_default != THEME.border_highlight
    assert THEME.radius_large > THEME.radius_medium > THEME.radius_small
