from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models.export_result import ExportOptions, ExportProgress
from app.services.export_service import ExportPreflightError, export_original_size


def parse_rgb(value: str) -> tuple[int, int, int]:
    normalized = value.strip().lstrip("#")
    if len(normalized) != 6:
        raise argparse.ArgumentTypeError(
            "Background must be a six-digit RGB hex color."
        )
    try:
        return tuple(
            int(normalized[offset : offset + 2], 16)
            for offset in (0, 2, 4)
        )
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "Background must be a six-digit RGB hex color."
        ) from error


def print_progress(progress: ExportProgress) -> None:
    if progress.slice_info is None:
        print(f"{progress.phase}: {progress.current}/{progress.total}")
        return
    print(
        f"{progress.phase}: {progress.current}/{progress.total} "
        f"slice={progress.slice_info.index} "
        f"size={progress.slice_info.width}x{progress.slice_info.height}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export PSD/PSB slices at original pixel dimensions."
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("--output-parent", type=Path)
    parser.add_argument("--zip", action="store_true", dest="create_zip")
    parser.add_argument("--allow-unverified", action="store_true")
    parser.add_argument(
        "--format",
        choices=("png", "jpeg"),
        default="png",
        dest="output_format",
    )
    parser.add_argument("--jpeg-quality", type=int, default=95)
    parser.add_argument(
        "--background",
        type=parse_rgb,
        default=(255, 255, 255),
        metavar="#RRGGBB",
    )
    parser.add_argument(
        "--color",
        choices=("auto", "preserve", "srgb"),
        default="auto",
        dest="color_policy",
    )
    parser.add_argument("--allow-mode-conversion", action="store_true")
    parser.add_argument(
        "--photoshop",
        choices=("disabled", "if_needed", "always"),
        default="disabled",
        dest="photoshop_fallback",
        help="Use Photoshop only when explicitly selected.",
    )
    parser.add_argument(
        "--allow-photoshop-launch",
        action="store_true",
        help="Allow starting Photoshop when no active instance exists.",
    )
    args = parser.parse_args()

    try:
        result = export_original_size(
            args.source,
            ExportOptions(
                output_parent=args.output_parent,
                create_zip=args.create_zip,
                allow_unverified_composite=args.allow_unverified,
                output_format=args.output_format,
                jpeg_quality=args.jpeg_quality,
                jpeg_background=args.background,
                color_policy=args.color_policy,
                allow_mode_conversion=args.allow_mode_conversion,
                photoshop_fallback=args.photoshop_fallback,
                photoshop_allow_launch=args.allow_photoshop_launch,
            ),
            progress_callback=print_progress,
        )
    except (ExportPreflightError, ValueError) as error:
        print(f"Export cannot start: {error}", file=sys.stderr)
        raise SystemExit(2) from error

    print(f"status: {result.status}")
    print(f"output: {result.output_directory}")
    print(f"format: {result.output_format}")
    print(f"color-policy: {result.color_policy}")
    print(f"composite-source: {result.composite_source}")
    print(f"exported: {len(result.exported_slices)}")
    if result.archive_path:
        print(f"zip: {result.archive_path}")
    if result.validation_json_path:
        print(f"validation-json: {result.validation_json_path}")
    if result.validation_text_path:
        print(f"validation-text: {result.validation_text_path}")
    for failure in result.failures:
        print(f"error: {failure.message}", file=sys.stderr)
    raise SystemExit(0 if result.success else 1)


if __name__ == "__main__":
    main()
