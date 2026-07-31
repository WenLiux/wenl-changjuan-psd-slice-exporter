# Stage 1 - Planned Data Model and Parser Extraction

Stage 1 must remain limited to data models, slice parsing, normalization, and
tests. Composite reading, image export, resizing, color management, Photoshop
automation, and GUI work remain out of scope.

## Planned model

Create a typed `SliceInfo` dataclass containing:

```text
index
slice_id
name
left
top
right
bottom
is_automatic
source_version
origin
slice_type
```

Calculated properties:

```text
width
height
bounds
is_full_canvas
```

## Parser work

1. Extract V6 parsing into a dedicated function.
2. Extract V7/V8 descriptor parsing into a dedicated function.
3. Preserve original record index.
4. Preserve Photoshop slice name.
5. Preserve origin and type metadata.
6. Normalize every coordinate to an integer.
7. Validate positive dimensions.
8. Validate canvas bounds without exporting.
9. Sort by `top`, `left`, then original `index`.
10. Return structured warnings instead of printing or raising raw errors.

## Automatic-slice policy

Tests must cover:

- automatic full-canvas slice plus user slices;
- only one automatic full-canvas slice;
- one user-created full-canvas slice;
- user-created full-canvas slice plus smaller slices;
- multiple full-canvas records;
- missing or unknown origin metadata.

Ambiguous user-created full-canvas slices must not be silently deleted.

## Required tests

- real V6 PSB fixture;
- real V8 PSD fixture;
- synthetic V7 descriptor fixture;
- byte-key and string-key descriptor bounds;
- duplicate coordinates;
- zero-width and zero-height slices;
- out-of-canvas coordinates;
- multi-column ordering;
- equal-position stable ordering;
- Chinese slice names;
- automatic-slice ambiguity cases.

## Compatibility rule

Keep the current legacy CLI file unchanged during Stage 1. Add a comparison
test proving that the new parser produces the same 14 effective slice bounds
for both verified fixtures before the exporter is allowed to use the new
model.

## Stage 1 completion criteria

- all V6/V7/V8 records normalize to `SliceInfo`;
- verified fixture bounds match the Stage 0 baseline;
- ambiguous full-canvas slices are surfaced, not deleted;
- all new public functions have type annotations;
- parser tests pass independently of image decoding;
- README and audit documentation are updated;
- Stage 1 is committed separately.
