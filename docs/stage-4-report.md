# Stage 4 - Target-Width Scaling

## Status

Stage 4 is complete. The exporter supports original width or one requested
canvas width while keeping every slice on the same global pixel grid.

## Added modules

```text
app/models/scale_plan.py
app/core/resizer.py
scripts/export_slices.py
```

## Global coordinate mapping

One scale is calculated from the complete canvas:

```text
scale = target_width / canvas_width
```

Every boundary uses the same rule:

```text
mapped = round(source_coordinate * scale)
```

Mapped slice dimensions are differences between mapped boundaries, not
independently rounded widths and heights.

This guarantees:

- adjacent bottom and top boundaries are identical;
- full-width slices receive the exact target width;
- no cumulative height rounding;
- the final slice reaches the mapped canvas bottom.

## Full-canvas strategy

When the estimated resized RGBA canvas is within the configured limit:

```text
resize the complete composite once with LANCZOS
  -> crop every slice using mapped boundaries
```

This is the default strategy for normal target widths such as 750, 790, 800,
and 1440 px.

## Low-memory strategy

When a complete resized canvas would exceed the configured memory limit:

```text
map each slice to the global output grid
  -> expand its output region by 8 px
  -> map that region back to the source pixel grid
  -> resize with LANCZOS
  -> crop away the expanded border
```

The source box uses the actual horizontal and rounded vertical output grids.
This prevents bottom-edge overflow when mapped canvas height is rounded.

On a deterministic gradient fixture, stitching all low-memory tiles is
pixel-identical to cropping one full resized canvas.

## Options and reporting

New options:

- target width;
- allow or block enlargement;
- full-resize memory limit;
- low-memory edge padding.

`ExportResult` now reports:

- effective target width;
- global scale;
- resize strategy: `none`, `full_canvas`, or `per_slice`.

Collision-safe directory names distinguish modes:

```text
source_slices_original
source_slices_750px
source_slices_750px_02
```

## Verified 750 px export

The real 1440 x 28164 PSD was exported at 750 px:

- 14 exported slices;
- every full-width slice is exactly 750 px;
- first mapped top is 0;
- last mapped bottom equals the mapped canvas height;
- every adjacent bottom equals the following top;
- sum of all slice heights equals the mapped canvas height;
- strategy selected: full-canvas resize.

## Tests

New coverage includes:

- 1440 to 750 global boundary mapping;
- gap-free and duplicate-free adjacent boundaries;
- no-upscale enforcement;
- full-canvas LANCZOS resize;
- low-memory pixel-grid equivalence;
- prepared target-width export metadata;
- target-width folder naming;
- real PSD 750 px export;
- all original-size compatibility tests.

Result:

```text
35 passed
```

## Stage 5 entry conditions

Stage 5 may add structured preflight and post-export validation for:

- duplicate slices;
- gaps;
- overlaps;
- out-of-canvas bounds;
- output count;
- output reopen and dimensions;
- empty and single-color content warnings;
- stitch-back comparison for original-size PNG;
- TXT and JSON reports.
