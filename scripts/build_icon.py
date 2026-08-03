from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from resvg_py import svg_to_bytes


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIRECTORY = PROJECT_ROOT / "packaging" / "assets"
SVG_PATH = ASSET_DIRECTORY / "WENL-Changjuan.svg"
PNG_PATH = ASSET_DIRECTORY / "WENL-Changjuan-1024.png"
ICO_PATH = ASSET_DIRECTORY / "WENL-Changjuan.ico"
ICON_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def main() -> int:
    png_bytes = svg_to_bytes(
        svg_path=str(SVG_PATH),
        width=1024,
        height=1024,
    )
    PNG_PATH.write_bytes(png_bytes)

    with Image.open(io.BytesIO(png_bytes)) as rendered:
        rendered.convert("RGBA").save(
            ICO_PATH,
            format="ICO",
            sizes=[(size, size) for size in ICON_SIZES],
        )

    print(ICO_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
