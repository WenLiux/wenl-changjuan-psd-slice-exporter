# PSD/PSB High-Fidelity Slice Exporter

Windows desktop tool project for exporting Photoshop slices without the legacy
8192-pixel long-edge downscaling behavior.

## Current status

Completed:

- Stage 0: legacy audit and pixel-level regression baseline.
- Stage 1: typed slice model and V6/V7/V8 parser extraction.
- Stage 2: reliable embedded-composite reader.
- Stage 3: collision-safe original-size folder export.
- Stage 4: globally aligned target-width scaling.
- Stage 5: structured preflight and post-export validation reports.
- Stage 6: PNG/JPEG encoding and explicit color handling.
- Stage 7: optional Photoshop high-fidelity fallback with source protection.
- Stage 8: responsive Windows desktop UI and reusable worker session.

Stage 9, Windows packaging and packaged-app verification, is the next planned
stage.

Reports:

- `docs/stage-0-audit.md`
- `docs/stage-1-report.md`
- `docs/stage-2-report.md`
- `docs/stage-3-report.md`
- `docs/stage-4-report.md`
- `docs/stage-5-report.md`
- `docs/stage-6-report.md`
- `docs/stage-7-report.md`
- `docs/stage-8-report.md`
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

## Target-width CLI

```powershell
python scripts/export_slices.py input.psb --width 750
python scripts/export_slices.py input.psd --width 1440 --no-upscale
```

Omit `--width` to preserve original dimensions.

## PNG, JPEG, and color options

PNG remains lossless and transparent by default:

```powershell
python scripts/export_slices.py input.psd --width 1440 --format png
```

JPEG defaults to quality 95, a white transparency background, and sRGB:

```powershell
python scripts/export_slices.py input.psd --width 1440 --format jpeg
python scripts/export_slices.py input.psd --format jpeg `
  --jpeg-quality 100 --background "#F5F5F5" --color srgb
```

PNG defaults to preserving the document ICC profile and channel values. JPEG
defaults to sRGB. CMYK, 16-bit, and unsupported modes stop before export unless
`--allow-mode-conversion` is supplied. Non-RGB conversion also requires a
compatible embedded ICC profile; Photoshop high-fidelity mode is the
recommended fallback when those safety conditions are not met.

## Photoshop high-fidelity fallback

The embedded merged image remains the default. Photoshop is never contacted
unless explicitly selected:

```powershell
python -m pip install -r requirements-photoshop.txt
python scripts/export_slices.py input.psb --photoshop if_needed
python scripts/export_slices.py input.psd --photoshop always
```

By default Photoshop must already be running with no open documents. Starting
it requires the separate `--allow-photoshop-launch` flag.

Fallback opens only a verified system-temporary copy, uses standard PNG Save
As rather than Save for Web, closes only its own temporary document without
saving, never quits Photoshop, and verifies the original SHA-256, size, and
modification time before and after. V1 Photoshop fallback is restricted to
8-bit RGB documents.

## Windows desktop application

Install the normal UI dependencies:

```powershell
python -m pip install -r requirements.txt
```

Install the optional Photoshop bridge when fallback is required:

```powershell
python -m pip install -r requirements-photoshop.txt
```

Start the application:

```powershell
python -m app.main
```

or:

```powershell
python scripts/run_gui.py
```

The UI supports file selection and drag-and-drop, original or custom width,
slice selection, PNG/JPEG and color controls, safe Photoshop fallback,
collision-safe output, ZIP creation, progress, cancellation, validation
reports, and repeat export without reparsing the open PSD/PSB.

Settings are stored at:

```text
%APPDATA%\PSD Slice Exporter\settings.json
```

Photoshop launch, unverified-composite use, and mode conversion are one-run
safety permissions and are never saved.

## Current test result

```text
135 passed
```

This includes the real Windows GUI smoke export. See
`docs/stage-8-report.md` for the verification matrix.
