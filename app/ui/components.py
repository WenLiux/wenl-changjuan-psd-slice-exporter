from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, Literal

import customtkinter as ctk
import tkinter as tk
from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageTk

from app.ui.theme import THEME


ButtonKind = Literal["primary", "secondary", "danger", "quiet"]


def ui_font(size: int = 13, *, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(
        family=THEME.font_family,
        size=size,
        weight=weight,
    )


class GlassCard(ctk.CTkFrame):
    """Static glass-like card built from supported CTk primitives."""

    def __init__(
        self,
        master: Any,
        *,
        emphasized: bool = False,
        secondary: bool = False,
        textured: bool = True,
        **kwargs: Any,
    ) -> None:
        kwargs.setdefault(
            "fg_color",
            THEME.bg_card_secondary if secondary else THEME.bg_card,
        )
        kwargs.setdefault("corner_radius", THEME.radius_large)
        kwargs.setdefault("border_width", 1)
        kwargs.setdefault(
            "border_color",
            THEME.border_emphasis if emphasized else THEME.border_default,
        )
        super().__init__(master, **kwargs)
        self._glass_emphasized = emphasized
        self._glass_textured = textured
        self._glass_photo: ImageTk.PhotoImage | None = None
        self._glass_item: int | None = None
        self._glass_after_id: str | None = None
        if textured:
            self.bind("<Configure>", self._schedule_glass_redraw, add="+")

    def _schedule_glass_redraw(self, event: tk.Event[tk.Misc]) -> None:
        width = self.winfo_width()
        height = self.winfo_height()
        if width < 8 or height < 8:
            return
        if self._glass_after_id is not None:
            self.after_cancel(self._glass_after_id)
        self._glass_after_id = self.after(
            70,
            lambda: self._draw_glass_surface(width, height),
        )

    def _draw_glass_surface(self, width: int, height: int) -> None:
        self._glass_after_id = None
        if not self.winfo_exists():
            return
        surface = _glass_surface_image(
            width,
            height,
            corner_radius=int(self.cget("corner_radius")),
            emphasized=self._glass_emphasized,
        )
        self._glass_photo = ImageTk.PhotoImage(surface)
        surface.close()
        if (
            self._glass_item is None
            or not self._canvas.type(self._glass_item)
        ):
            self._glass_item = self._canvas.create_image(
                0,
                0,
                anchor="nw",
                image=self._glass_photo,
            )
        else:
            self._canvas.itemconfigure(
                self._glass_item,
                image=self._glass_photo,
            )
        self._canvas.tag_raise(self._glass_item)


def _glass_surface_image(
    width: int,
    height: int,
    *,
    corner_radius: int,
    emphasized: bool,
) -> Image.Image:
    gradient = Image.linear_gradient("L").resize(
        (width, height),
        Image.Resampling.BILINEAR,
    )
    surface = ImageOps.colorize(
        gradient,
        black="#142136" if emphasized else "#121E31",
        white="#0C1728",
    ).convert("RGBA")

    glow = Image.new("RGBA", surface.size, (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        (
            -width * 0.2,
            -height * 0.65,
            width * 0.82,
            height * 0.45,
        ),
        fill=(66, 96, 169, 34 if emphasized else 22),
    )
    glow_draw.ellipse(
        (
            width * 0.64,
            -height * 0.32,
            width * 1.14,
            height * 0.32,
        ),
        fill=(92, 79, 176, 20 if emphasized else 12),
    )
    glow = glow.filter(
        ImageFilter.GaussianBlur(radius=max(18, min(width, height) // 8))
    )
    surface = Image.alpha_composite(surface, glow)

    mask = Image.new("L", surface.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (1, 1, width - 2, height - 2),
        radius=max(2, corner_radius - 1),
        fill=255,
    )
    surface.putalpha(mask)
    ImageDraw.Draw(surface).line(
        (
            max(corner_radius, width * 0.07),
            2,
            width * 0.6,
            2,
        ),
        fill=(116, 143, 204, 72 if emphasized else 45),
        width=1,
    )
    return surface


def make_button(
    master: Any,
    *,
    text: str,
    command: Callable[[], None],
    kind: ButtonKind = "secondary",
    width: int = 96,
    height: int = 38,
    image: ctk.CTkImage | None = None,
    **kwargs: Any,
) -> ctk.CTkButton:
    styles: dict[ButtonKind, dict[str, Any]] = {
        "primary": {
            "fg_color": THEME.accent_primary,
            "hover_color": THEME.accent_hover,
            "border_color": THEME.accent_secondary,
            "border_width": 1,
            "text_color": THEME.text_primary,
        },
        "secondary": {
            "fg_color": THEME.bg_card_secondary,
            "hover_color": THEME.bg_hover,
            "border_color": THEME.border_default,
            "border_width": 1,
            "text_color": THEME.text_primary,
        },
        "danger": {
            "fg_color": THEME.danger_bg,
            "hover_color": THEME.danger_hover,
            "border_color": THEME.danger,
            "border_width": 1,
            "text_color": THEME.danger_text,
        },
        "quiet": {
            "fg_color": "transparent",
            "hover_color": THEME.bg_hover,
            "border_color": THEME.border_default,
            "border_width": 1,
            "text_color": THEME.text_secondary,
        },
    }
    options = styles[kind] | kwargs
    return ctk.CTkButton(
        master,
        text=text,
        command=command,
        width=width,
        height=height,
        corner_radius=THEME.radius_small,
        font=ui_font(13, weight="bold"),
        image=image,
        compound="left",
        **options,
    )


def make_entry(
    master: Any,
    *,
    textvariable: tk.Variable,
    width: int | None = None,
    placeholder_text: str = "",
) -> ctk.CTkEntry:
    options: dict[str, Any] = {
        "master": master,
        "textvariable": textvariable,
        "height": 38,
        "corner_radius": THEME.radius_small,
        "fg_color": THEME.bg_input,
        "border_color": THEME.border_default,
        "border_width": 1,
        "text_color": THEME.text_primary,
        "placeholder_text_color": THEME.text_muted,
        "placeholder_text": placeholder_text,
        "font": ui_font(13),
    }
    if width is not None:
        options["width"] = width
    return ctk.CTkEntry(**options)


def make_option_menu(
    master: Any,
    *,
    values: Sequence[str],
    variable: tk.StringVar,
    command: Callable[[str], None] | None = None,
) -> ctk.CTkOptionMenu:
    return ctk.CTkOptionMenu(
        master,
        values=list(values),
        variable=variable,
        command=command,
        height=38,
        corner_radius=THEME.radius_small,
        fg_color=THEME.bg_input,
        button_color=THEME.bg_input,
        button_hover_color=THEME.bg_hover,
        dropdown_fg_color=THEME.bg_card_secondary,
        dropdown_hover_color=THEME.bg_hover,
        dropdown_text_color=THEME.text_primary,
        text_color=THEME.text_primary,
        font=ui_font(13),
        dropdown_font=ui_font(13),
        anchor="w",
    )


def make_checkbox(
    master: Any,
    *,
    text: str,
    variable: tk.BooleanVar,
    command: Callable[[], None] | None = None,
) -> ctk.CTkCheckBox:
    return ctk.CTkCheckBox(
        master,
        text=text,
        variable=variable,
        command=command,
        width=24,
        height=24,
        corner_radius=5,
        border_width=2,
        fg_color=THEME.accent_primary,
        hover_color=THEME.accent_hover,
        border_color=THEME.border_highlight,
        text_color=THEME.text_secondary,
        text_color_disabled=THEME.text_disabled,
        font=ui_font(13),
    )


def make_switch(
    master: Any,
    *,
    text: str,
    variable: tk.BooleanVar,
    command: Callable[[], None] | None = None,
) -> ctk.CTkSwitch:
    return ctk.CTkSwitch(
        master,
        text=text,
        variable=variable,
        command=command,
        progress_color=THEME.accent_primary,
        button_color=THEME.text_primary,
        button_hover_color=THEME.text_primary,
        fg_color=THEME.border_default,
        text_color=THEME.text_secondary,
        font=ui_font(13),
    )


def make_segmented(
    master: Any,
    *,
    values: Sequence[str],
    variable: tk.StringVar,
    command: Callable[[str], None],
) -> ctk.CTkSegmentedButton:
    return ctk.CTkSegmentedButton(
        master,
        values=list(values),
        variable=variable,
        command=command,
        height=40,
        corner_radius=THEME.radius_small,
        border_width=1,
        fg_color=THEME.bg_card_secondary,
        unselected_color=THEME.bg_card_secondary,
        unselected_hover_color=THEME.bg_hover,
        selected_color=THEME.accent_primary,
        selected_hover_color=THEME.accent_hover,
        text_color=THEME.text_primary,
        text_color_disabled=THEME.text_disabled,
        font=ui_font(13),
    )


def section_label(master: Any, text: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        master,
        text=text,
        anchor="w",
        text_color=THEME.text_primary,
        font=ui_font(15, weight="bold"),
    )


def make_icon(
    name: Literal["upload", "sparkle", "folder", "report", "close"],
    *,
    size: int = 18,
    color: str = "#F0F4FF",
) -> ctk.CTkImage:
    scale = 3
    canvas_size = size * scale
    image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    stroke = max(3, scale * 2)

    def point(x: float, y: float) -> tuple[int, int]:
        return int(x * canvas_size), int(y * canvas_size)

    if name == "upload":
        draw.line([point(0.5, 0.78), point(0.5, 0.2)], fill=color, width=stroke)
        draw.line([point(0.28, 0.42), point(0.5, 0.2), point(0.72, 0.42)], fill=color, width=stroke, joint="curve")
    elif name == "sparkle":
        draw.line([point(0.5, 0.1), point(0.5, 0.9)], fill=color, width=stroke)
        draw.line([point(0.1, 0.5), point(0.9, 0.5)], fill=color, width=stroke)
        draw.line([point(0.23, 0.23), point(0.77, 0.77)], fill=color, width=stroke)
        draw.line([point(0.77, 0.23), point(0.23, 0.77)], fill=color, width=stroke)
    elif name == "folder":
        draw.line([point(0.12, 0.35), point(0.34, 0.35), point(0.42, 0.24), point(0.78, 0.24), point(0.88, 0.38), point(0.82, 0.78), point(0.14, 0.78), point(0.12, 0.35)], fill=color, width=stroke, joint="curve")
    elif name == "report":
        draw.rounded_rectangle([*point(0.22, 0.12), *point(0.78, 0.88)], radius=stroke * 2, outline=color, width=stroke)
        draw.line([point(0.34, 0.38), point(0.66, 0.38)], fill=color, width=stroke)
        draw.line([point(0.34, 0.55), point(0.66, 0.55)], fill=color, width=stroke)
        draw.line([point(0.34, 0.72), point(0.58, 0.72)], fill=color, width=stroke)
    else:
        draw.line([point(0.24, 0.24), point(0.76, 0.76)], fill=color, width=stroke)
        draw.line([point(0.76, 0.24), point(0.24, 0.76)], fill=color, width=stroke)

    return ctk.CTkImage(
        light_image=image,
        dark_image=image,
        size=(size, size),
    )


def make_ambient_background(
    width: int = 1240,
    height: int = 820,
) -> Image.Image:
    """Create one static, low-contrast backdrop for the window."""

    sample_width = max(240, width // 4)
    sample_height = max(160, height // 4)
    top = (6, 11, 21)
    bottom = (8, 17, 32)
    base = Image.new("RGBA", (sample_width, sample_height))
    pixels = base.load()
    for y in range(sample_height):
        ratio = y / max(1, sample_height - 1)
        row_color = tuple(
            round(start + (end - start) * ratio)
            for start, end in zip(top, bottom, strict=True)
        ) + (255,)
        for x in range(sample_width):
            pixels[x, y] = row_color

    glow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(glow)
    draw.ellipse(
        (
            -sample_width * 0.2,
            -sample_height * 0.45,
            sample_width * 0.7,
            sample_height * 0.48,
        ),
        fill=(45, 76, 160, 34),
    )
    draw.ellipse(
        (
            sample_width * 0.58,
            -sample_height * 0.25,
            sample_width * 1.18,
            sample_height * 0.38,
        ),
        fill=(83, 67, 169, 22),
    )
    draw.ellipse(
        (
            sample_width * 0.46,
            sample_height * 0.7,
            sample_width * 1.12,
            sample_height * 1.2,
        ),
        fill=(29, 70, 143, 18),
    )
    glow = glow.filter(
        ImageFilter.GaussianBlur(radius=max(22, sample_width // 10))
    )
    composed = Image.alpha_composite(base, glow)
    return composed.resize((width, height), Image.Resampling.BICUBIC)


__all__ = [
    "GlassCard",
    "make_button",
    "make_checkbox",
    "make_entry",
    "make_icon",
    "make_ambient_background",
    "make_option_menu",
    "make_segmented",
    "make_switch",
    "section_label",
    "ui_font",
]
