# Stage 3 - Original-Size Folder Export

## Status

Stage 3 is complete. The production service exports normalized user slices at
their original pixel dimensions without using the legacy Save for Web path.

## Added modules

```text
app/models/export_result.py
app/services/export_service.py
app/utils/paths.py
scripts/export_original_size.py
```

## Export workflow

```text
open PSD/PSB
  -> parse normalized user slices
  -> read embedded merged composite
  -> reject missing or unreliable data
  -> atomically create a collision-safe folder
  -> crop original-size slices
  -> write PNG through a temporary file
  -> atomically rename the completed file
  -> reopen and verify dimensions
  -> optionally create ZIP
```

The service does not modify or save the source PSD/PSB.

## Output safety

Default output:

```text
<source folder>\<source name>_slices_original
```

Collisions produce:

```text
<source name>_slices_original_02
<source name>_slices_original_03
```

The directory is created atomically with `exist_ok=False`. Existing files are
never reused or overwritten, and stale files cannot enter the current ZIP.

ZIP behavior:

- disabled by default;
- created only after all selected slices export successfully;
- skipped for cancelled or partially failed runs;
- stored beside the output directory.

## Image behavior

- original slice coordinates and dimensions;
- PNG output;
- RGBA transparency preserved;
- original ICC bytes embedded when present;
- no color conversion;
- no resizing;
- crop objects released after each slice;
- full composite closed by the top-level service after export.

PNG/JPEG format choice and explicit color policy remain reserved for Stage 6.

## Structured results

`ExportResult` reports:

- completed, completed-with-errors, or cancelled status;
- output directory;
- optional ZIP path;
- every exported slice;
- per-slice failures;
- parser issues;
- composite warning;
- source unchanged status;
- elapsed time.

Progress callbacks report:

```text
starting
exporting
written
archiving
```

Cancellation is checked between slices so a file write is never deliberately
interrupted halfway.

## Real fixture verification

Both verified fixtures passed through the new service:

| Fixture | Exported | Width | ZIP default | Source unchanged |
| --- | ---: | ---: | --- | --- |
| PSD V8 | 14 | 1440 | Off | Yes |
| PSB V6 | 14 | 1440 | Off | Yes |

For both:

- the complete output filename list matches the Stage 0 baseline;
- first and last slice decoded pixels match the baseline;
- canvas-derived dimensions match;
- no source size or modification-time change occurred.

## Tests

Coverage includes:

- real PSD and PSB original-size export;
- collision-safe folder numbering;
- ZIP opt-in and integrity;
- cancellation between slices;
- progress events;
- unverified-composite refusal and explicit override;
- no-exportable-slices preflight failure;
- all Stage 0 through Stage 2 regressions.

Result:

```text
29 passed
```

## Stage 4 entry conditions

Stage 4 may add target-width scaling that:

- calculates one global scale from canvas width;
- maps every boundary with the same rounding rule;
- normally resizes the complete composite once, then crops;
- guarantees full-width slices receive the requested width;
- avoids missing or repeated pixel rows at adjacent boundaries;
- warns before enlargement and supports a no-upscale option.
