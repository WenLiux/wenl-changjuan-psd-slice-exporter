from __future__ import annotations

from pathlib import Path


def create_collision_safe_directory(
    parent: Path,
    base_name: str,
    *,
    reserve_zip_path: bool = False,
    maximum_attempts: int = 9999,
) -> Path:
    """Atomically create a new directory without overwriting prior output."""

    parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(1, maximum_attempts + 1):
        suffix = "" if attempt == 1 else f"_{attempt:02d}"
        candidate = parent / f"{base_name}{suffix}"
        if reserve_zip_path and candidate.with_suffix(".zip").exists():
            continue
        try:
            candidate.mkdir(exist_ok=False)
        except FileExistsError:
            continue
        return candidate
    raise FileExistsError(
        f"Unable to create a unique output directory for '{base_name}'."
    )
