from __future__ import annotations

import argparse
import importlib
import json
import sys
import traceback
from pathlib import Path

from app.models.export_result import ExportOptions
from app.services.export_service import export_slices


def _probe_photoshop_bindings() -> tuple[bool, str | None]:
    try:
        for module_name in ("pythoncom", "pywintypes", "win32com.client"):
            importlib.import_module(module_name)
    except Exception as error:
        return False, f"{type(error).__name__}: {error}"
    return True, None


def _probe_tkdnd() -> tuple[bool, str | None]:
    root = None
    try:
        import tkinter as tk

        from tkinterdnd2 import TkinterDnD

        root = tk.Tk()
        root.withdraw()
        version = str(TkinterDnD.require(root))
    except Exception as error:
        return False, f"{type(error).__name__}: {error}"
    finally:
        if root is not None:
            root.destroy()
    return True, version


def _write_smoke_result(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_package_smoke(
    source: Path,
    output_parent: Path,
    result_path: Path,
    *,
    target_width: int,
) -> int:
    bindings_available, bindings_error = _probe_photoshop_bindings()
    tkdnd_available, tkdnd_detail = _probe_tkdnd()
    payload: dict[str, object] = {
        "source": str(source),
        "target_width": target_width,
        "frozen": bool(getattr(sys, "frozen", False)),
        "executable": sys.executable,
        "photoshop_bindings_available": bindings_available,
        "photoshop_bindings_error": bindings_error,
        "tkdnd_available": tkdnd_available,
        "tkdnd_detail": tkdnd_detail,
    }
    try:
        result = export_slices(
            source,
            ExportOptions(
                output_parent=output_parent,
                target_width=target_width,
                allow_upscale=False,
                naming_rule="sequence_dimensions",
            ),
        )
        payload.update(
            {
                "status": result.status,
                "success": result.success,
                "slice_count": len(result.exported_slices),
                "output_directory": str(result.output_directory),
                "validation_passed": result.validation_report.passed,
                "source_unchanged": result.source_unchanged,
            }
        )
        return_code = (
            0
            if result.success and bindings_available and tkdnd_available
            else 1
        )
    except Exception as error:
        payload.update(
            {
                "status": "failed",
                "success": False,
                "error_type": type(error).__name__,
                "error": str(error),
                "traceback": traceback.format_exc(),
            }
        )
        return_code = 1
    _write_smoke_result(result_path, payload)
    return return_code


def _argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--legacy-ui", action="store_true")
    parser.add_argument("--web-debug", action="store_true")
    parser.add_argument("--package-smoke-source", type=Path)
    parser.add_argument("--package-smoke-output", type=Path)
    parser.add_argument("--package-smoke-result", type=Path)
    parser.add_argument(
        "--package-smoke-width",
        type=int,
        default=750,
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    arguments, _ = _argument_parser().parse_known_args(argv)
    if arguments.package_smoke_source is not None:
        if (
            arguments.package_smoke_output is None
            or arguments.package_smoke_result is None
        ):
            return 2
        return run_package_smoke(
            arguments.package_smoke_source,
            arguments.package_smoke_output,
            arguments.package_smoke_result,
            target_width=arguments.package_smoke_width,
        )

    if arguments.legacy_ui:
        import customtkinter as ctk

        from app.ui.main_window import MainWindow

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        app = MainWindow()
        app.mainloop()
        return 0

    from app.desktop import run_webview

    return run_webview(debug=arguments.web_debug)


if __name__ == "__main__":
    raise SystemExit(main())
