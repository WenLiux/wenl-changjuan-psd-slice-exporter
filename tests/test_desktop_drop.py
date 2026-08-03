from pathlib import Path

from app.desktop.window import dropped_file_paths


def test_dropped_file_paths_reads_pywebview_full_paths() -> None:
    event = {
        "dataTransfer": {
            "files": [
                {
                    "name": "详情切片.psb",
                    "pywebviewFullPath": r"C:\素材\详情切片.psb",
                },
                {
                    "name": "第二个.psd",
                    "pywebviewFullPath": r"D:\设计\第二个.psd",
                },
            ]
        }
    }

    assert dropped_file_paths(event) == (
        Path(r"C:\素材\详情切片.psb"),
        Path(r"D:\设计\第二个.psd"),
    )


def test_dropped_file_paths_ignores_incomplete_browser_payloads() -> None:
    assert dropped_file_paths({}) == ()
    assert dropped_file_paths({"dataTransfer": {"files": []}}) == ()
    assert dropped_file_paths(
        {"dataTransfer": {"files": [{"name": "missing-path.psd"}]}}
    ) == ()
