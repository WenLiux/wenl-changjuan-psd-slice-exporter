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
- Stage 9: reproducible Windows onedir packaging and packaged-app verification.
- Stage 10: final release acceptance and Windows artifact handoff.
- Version 0.2.0: restrained blue-glass UI redesign with reusable visual
  components and responsive verification.

Version 0.2.0 is complete. Version 0.1.0 remains documented as the original
functional release baseline.

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
- `docs/stage-9-report.md`
- `docs/stage-10-acceptance.md`
- `docs/ui-redesign-report.md`
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

Version 0.2.0 adds a centralized dark blue-glass theme, static ambient and card
gradients, restrained highlights, rounded preview and list surfaces, consistent
primary/secondary/danger controls, and line icons. The effects redraw only
after a resize settles; there is no continuous animation loop.

Settings are stored at:

```text
%APPDATA%\PSD Slice Exporter\settings.json
```

Photoshop launch, unverified-composite use, and mode conversion are one-run
safety permissions and are never saved.

## Windows release build

Create a dedicated release environment and install the pinned build
dependencies:

```powershell
python -m venv .venv-release
.\.venv-release\Scripts\python.exe -m pip install -r requirements-build.txt
```

Build the windowed onedir application:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_windows.ps1
```

The application is created at:

```text
dist\PSD-PSB-Slice-Exporter\PSD-PSB-Slice-Exporter.exe
```

Keep the EXE, `_internal` directory, and `README-CN.txt` together. The
distributable Windows ZIP is written to `release` and preserves that complete
folder structure.

## Current test result

```text
140 passed
```

This includes both pinned PSD/PSB fixtures and the real Windows GUI export. The
0.2.0 packaged application was additionally tested against both fixtures,
launched as a responding GUI, and run after extracting its distributable ZIP.
See `docs/ui-redesign-report.md` for the release matrix.
