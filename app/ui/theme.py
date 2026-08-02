from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UiTheme:
    """Shared visual tokens for the desktop interface."""

    bg_window: str = "#080D18"
    bg_card: str = "#0E1829"
    bg_card_secondary: str = "#121E32"
    bg_input: str = "#0B1424"
    bg_input_disabled: str = "#0A111D"
    bg_hover: str = "#1A2943"
    bg_selected: str = "#14213A"

    border_default: str = "#293A57"
    border_subtle: str = "#1B2940"
    border_emphasis: str = "#3C5076"
    border_highlight: str = "#6079C8"
    highlight_inner: str = "#536A99"

    text_primary: str = "#F0F4FF"
    text_secondary: str = "#AAB5CA"
    text_muted: str = "#74829B"
    text_disabled: str = "#566277"

    accent_primary: str = "#415AD8"
    accent_secondary: str = "#6B7CF0"
    accent_hover: str = "#526BE6"
    accent_pressed: str = "#334DC5"
    accent_soft: str = "#243569"

    danger: str = "#B65373"
    danger_bg: str = "#52263B"
    danger_hover: str = "#683049"
    danger_text: str = "#F0A6B8"
    warning: str = "#D7A84D"

    radius_small: int = 9
    radius_medium: int = 14
    radius_large: int = 20

    spacing_small: int = 8
    spacing_medium: int = 14
    spacing_large: int = 22

    shadow_card: str = "#060A12"
    shadow_accent: str = "#101D38"
    preview_glow: str = "#172A4A"

    font_family: str = "Microsoft YaHei UI"
    font_fallback: str = "Segoe UI"


THEME = UiTheme()


__all__ = ["THEME", "UiTheme"]
