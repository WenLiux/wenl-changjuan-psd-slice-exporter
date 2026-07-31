from __future__ import annotations

import re


_INVALID_WINDOWS_CHARACTERS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_WINDOWS_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def safe_filename_component(value: str, *, fallback: str) -> str:
    """Return a bounded Windows-safe filename component."""

    normalized = _INVALID_WINDOWS_CHARACTERS.sub("_", value.strip())
    normalized = re.sub(r"\s+", " ", normalized).rstrip(" .")
    if not normalized:
        normalized = fallback
    if normalized.upper() in _RESERVED_WINDOWS_NAMES:
        normalized = f"_{normalized}"
    return normalized[:80].rstrip(" .") or fallback
