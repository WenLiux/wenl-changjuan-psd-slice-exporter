from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.models.export_result import ExportOptions, ExportProgress
from app.services.export_service import ExportPreflightError, export_original_size


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
    args = parser.parse_args()

    try:
        result = export_original_size(
            args.source,
            ExportOptions(
                output_parent=args.output_parent,
                create_zip=args.create_zip,
                allow_unverified_composite=args.allow_unverified,
            ),
            progress_callback=print_progress,
        )
    except ExportPreflightError as error:
        print(f"Export cannot start: {error}", file=sys.stderr)
        raise SystemExit(2) from error

    print(f"status: {result.status}")
    print(f"output: {result.output_directory}")
    print(f"exported: {len(result.exported_slices)}")
    if result.archive_path:
        print(f"zip: {result.archive_path}")
    for failure in result.failures:
        print(f"error: {failure.message}", file=sys.stderr)
    raise SystemExit(0 if result.success else 1)


if __name__ == "__main__":
    main()
