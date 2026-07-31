# Stage 5 - Validation Reports

## Status

Stage 5 is complete. Every production export now receives structured preflight
and post-export validation and writes human-readable TXT plus machine-readable
JSON reports by default.

## Added modules

```text
app/models/validation_report.py
app/core/validator.py
```

## Preflight validation

Checks:

- non-positive dimensions;
- out-of-canvas coordinates;
- duplicate bounds;
- overlapping slices;
- uncovered Y ranges for full-width vertical slice sets;
- coverage of the canvas bottom.

Coordinate errors block export. Gaps, overlaps, and duplicates are retained as
warnings so the UI can ask the user instead of silently modifying data.

## Post-export validation

Checks:

- expected versus actual output count;
- per-slice export failures;
- missing or zero-byte files;
- image reopen and decode;
- output dimensions;
- fully transparent content;
- single-color content.

For original-size output, every PNG is compared directly with the corresponding
crop from the embedded merged composite. This avoids allocating a second
full-height stitched canvas while still detecting any pixel difference.

Target-width output is structurally validated but does not use strict pixel
comparison because resampling intentionally changes pixels.

## Reports

Each successful output directory contains:

```text
validation_report.json
validation_report.txt
```

The JSON report contains:

- overall pass/fail;
- warning and error counts;
- phase;
- issue code;
- severity;
- user-readable message;
- involved slice indices;
- relevant coordinates.

Reports are written before optional ZIP creation, so the ZIP includes the
current run's reports.

## Tests

Coverage includes:

- overlap detection;
- duplicate detection;
- vertical-gap detection;
- original-size pixel mismatch;
- JSON report output;
- TXT report output;
- real PSD and PSB report generation;
- ZIP report inclusion;
- all Stage 0 through Stage 4 regressions.

Result:

```text
38 passed
```

## Stage 6 entry conditions

Stage 6 may add:

- PNG and JPEG format selection;
- JPEG quality 1 through 100;
- explicit alpha flattening background;
- preserve-ICC and convert-to-sRGB policies;
- user confirmation for CMYK, 16-bit, and unsupported modes;
- format-aware validation without strict JPEG pixel comparison.
