from pathlib import Path

from app import __version__
from app.config.brand import (
    BRAND_NAME,
    FULL_PRODUCT_NAME,
    FUNCTIONAL_SLOGAN,
    VERSION,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_python_brand_configuration_is_consistent() -> None:
    assert BRAND_NAME == "WENL / 长卷"
    assert "PSD / PSB" in FULL_PRODUCT_NAME
    assert FUNCTIONAL_SLOGAN == "超长画布，原样切出。"
    assert __version__ == VERSION


def test_dark_client_uses_explicit_light_logo() -> None:
    app_source = (PROJECT_ROOT / "frontend/src/App.tsx").read_text(
        encoding="utf-8"
    )
    white_logo = (
        PROJECT_ROOT / "frontend/src/assets/brand/logo-white.svg"
    ).read_text(encoding="utf-8")
    black_logo = (
        PROJECT_ROOT / "frontend/src/assets/brand/logo-black.svg"
    ).read_text(encoding="utf-8")

    assert "logo-white.svg" in app_source
    assert "logo-black.svg" not in app_source
    assert "#F4F5F7" in white_logo
    assert "#111111" in black_logo


def test_windows_icon_uses_explicit_light_symbol() -> None:
    icon_svg = (
        PROJECT_ROOT / "packaging/assets/WENL-Changjuan.svg"
    ).read_text(encoding="utf-8")
    icon_path = PROJECT_ROOT / "packaging/assets/WENL-Changjuan.ico"

    assert "#F4F5F7" in icon_svg
    assert "fill: currentColor" not in icon_svg
    assert icon_path.is_file()
    assert icon_path.stat().st_size > 10_000
