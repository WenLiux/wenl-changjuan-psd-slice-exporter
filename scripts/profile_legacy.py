from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import psutil


def process_tree_rss(process: psutil.Process) -> int:
    processes = [process]
    try:
        processes.extend(process.children(recursive=True))
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    total = 0
    for current in processes:
        try:
            total += current.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return total


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    project_root = Path(__file__).resolve().parents[1]
    exporter = project_root / "legacy" / "export_psd_slices_1440.py"
    command = [sys.executable, str(exporter), str(args.source), str(args.output)]

    started = time.perf_counter()
    child = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    process = psutil.Process(child.pid)
    peak_rss = 0
    while child.poll() is None:
        peak_rss = max(peak_rss, process_tree_rss(process))
        time.sleep(0.05)

    stdout, stderr = child.communicate()
    elapsed = time.perf_counter() - started
    result = {
        "source": str(args.source),
        "exit_code": child.returncode,
        "elapsed_seconds": round(elapsed, 3),
        "peak_rss_mib": round(peak_rss / (1024 * 1024), 1),
        "stdout": stdout,
        "stderr": stderr,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(child.returncode)


if __name__ == "__main__":
    main()
