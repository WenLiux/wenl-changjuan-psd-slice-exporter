# PSD/PSB High-Fidelity Slice Exporter

Windows desktop tool project for exporting Photoshop slices without the legacy
8192-pixel long-edge downscaling behavior.

## Current status

Completed:

- Stage 0: legacy audit and pixel-level regression baseline.
- Stage 1: typed slice model and V6/V7/V8 parser extraction.
- Stage 2: reliable embedded-composite reader.
- Stage 3: collision-safe original-size folder export.

Stage 4, target-width scaling, is the next planned stage. The desktop UI has
not started.

Reports:

- `docs/stage-0-audit.md`
- `docs/stage-1-report.md`
- `docs/stage-2-report.md`
- `docs/stage-3-report.md`
- `docs/stage-1-checklist.md`

## Legacy exporter

The reviewed standalone implementation is kept at:

```text
legacy/export_psd_slices_1440.py
```

It remains runnable as a command-line script:

```powershell
python legacy/export_psd_slices_1440.py input.psd output-folder
```

## Stage 0 regression tests

The large PSD/PSB fixtures are not copied into Git. Set their paths through
environment variables:

```powershell
$env:PSD_SLICE_V8_FIXTURE = 'C:\path\to\sample.psd'
$env:PSD_SLICE_V6_FIXTURE = 'C:\path\to\sample.psb'
python -m pytest
```

See `tests/fixtures/README.md` for the pinned fixture fingerprints.

## Original-size service CLI

```powershell
python scripts/export_original_size.py input.psd
python scripts/export_original_size.py input.psb --output-parent D:\Exports --zip
```

ZIP output is disabled unless `--zip` is provided. Every run creates a new,
collision-safe output directory.

## Current test result

```text
29 passed
```
