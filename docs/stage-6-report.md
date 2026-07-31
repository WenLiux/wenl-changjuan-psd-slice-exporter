# Stage 6 - PNG, JPEG, and Color Handling

## Status

Stage 6 is complete. The export service now has an explicit image-encoding
layer for PNG and JPEG, with format-aware alpha, ICC, validation, and source
mode safety rules.

## Added module

```text
app/core/image_encoder.py
```

The encoding layer builds and validates one immutable plan before an output
directory is created. Each crop is then prepared and encoded according to that
plan.

## Format behavior

PNG:

- remains the default;
- preserves RGBA channels and transparency;
- uses the configured compression level from 0 through 9;
- keeps source channel values when the color policy is `preserve`;
- uses `.png` filenames.

JPEG:

- accepts quality from 1 through 100, default 95;
- always writes RGB;
- explicitly composites transparency over a selected RGB background;
- uses white `(255, 255, 255)` by default;
- writes 4:4:4 chroma sampling for high-fidelity output;
- uses `.jpg` filenames.

Temporary files are still atomically renamed only after Pillow finishes
encoding them. Every output is reopened, format-checked, dimension-checked,
and, for JPEG, RGB-mode-checked.

## Color policies

Available policies:

```text
auto
preserve
srgb
```

Safe `auto` defaults:

| Format | Resolved policy |
| --- | --- |
| PNG | Preserve original ICC and channel values |
| JPEG | Convert to or tag as sRGB |

When an embedded source ICC profile exists, `srgb` uses Pillow LittleCMS to
convert pixels and embeds a generated sRGB profile. For an untagged 8-bit RGB
document, existing channel values are treated as sRGB and the sRGB profile is
embedded without changing those values.

`preserve` performs no color conversion and embeds the original ICC bytes when
available.

## Mode and depth safety

The automatic path is limited to:

```text
Photoshop RGB + 8-bit + decoded RGB/RGBA
```

CMYK, non-RGB, 16-bit, and otherwise unsupported combinations require explicit
confirmation before output is created. The error includes the original
Photoshop color mode, bit depth, and decoded Pillow mode.

Confirmation does not bypass color safety. A non-RGB conversion to sRGB also
requires a readable ICC profile that can build a transform for the decoded
pixel mode. A preserve-profile request is rejected whenever the selected
encoder would first have to convert those pixels to another color space.

The caller is directed to either:

- explicitly confirm a managed, compatible conversion; or
- use the planned Photoshop high-fidelity fallback.

The CLI exposes confirmation as `--allow-mode-conversion`. There is no silent
fallback. CMYK/LAB composite transparency that psd-tools cannot represent is
detected from the PSD channel metadata and rejected for Photoshop fallback
instead of being dropped.

## Validation behavior

Strict pixel comparison is now enabled only for lossless, original-size PNG
whose resolved color policy is `preserve`.

JPEG, resized output, and color-converted PNG still receive structural
validation:

- file count;
- successful reopen and decode;
- mapped dimensions;
- empty files;
- transparent or constant-color warnings;
- per-slice failure reporting.

Lossy JPEG output is not incorrectly failed by exact pixel comparison.

## CLI examples

```powershell
python scripts/export_slices.py input.psb --width 1440
python scripts/export_slices.py input.psb --width 1440 --format jpeg
python scripts/export_slices.py input.psb --format jpeg `
  --jpeg-quality 95 --background "#FFFFFF" --color srgb
python scripts/export_original_size.py input.psd --format png --color preserve
```

## Tests

New coverage includes:

- per-format default color policies;
- JPEG quality bounds;
- PNG alpha and ICC preservation;
- JPEG RGB output;
- selected-background alpha compositing;
- embedded sRGB profile output;
- format, RGB/alpha, and ICC-aware validation;
- unsupported color/depth refusal before output creation;
- explicit mode-conversion confirmation;
- invalid ICC rejection for requested conversion;
- ICC-to-pixel-mode compatibility preflight;
- LAB A-channel versus true alpha detection;
- non-representable CMYK/LAB transparency refusal;
- grayscale output validation;
- all Stage 0 through Stage 5 regressions against both real fixtures.

Result:

```text
51 passed
```

## Stage 7 entry conditions

Stage 7 can implement the Photoshop high-fidelity fallback for:

- missing or unreliable embedded composites;
- unsupported color modes and bit depths;
- cases where application-level color conversion is not acceptable.

The fallback must operate only on a temporary source copy, track document
ownership, never save or close pre-existing user documents, never quit
Photoshop, and verify the original source hash before and after automation.
