# Stage 2 - Reliable Composite Reader

## Status

Stage 2 is complete. Production code can now read Photoshop-saved merged image
data without silently invoking psd-tools layer compositing.

## Added modules

```text
app/models/composite_result.py
app/core/composite_reader.py
```

## High-fidelity policy

The reader only calls:

```python
psd.topil(apply_icc=False)
```

It never calls:

```python
psd.composite()
```

In psd-tools 1.14.2, `topil()` reads stored merged image channels, while
`composite()` is the separate API that can invoke third-party layer rendering.

Using `apply_icc=False` preserves stored channel values. ICC conversion is
deferred to the explicit color-management stage.

## Result model

`CompositeResult` reports:

- decoded image or `None`;
- source classification;
- canvas width and height;
- PSD color mode and bit depth;
- Pillow image mode;
- original ICC profile bytes;
- alpha availability;
- reliability status;
- warning;
- user-readable error;
- whether Photoshop fallback is required.

Source classifications:

```text
embedded_merged
embedded_merged_unverified
missing
invalid
```

## Reliability rules

1. `VERSION_INFO.has_composite == True`
   - decode merged data;
   - mark reliable.
2. `VERSION_INFO.has_composite == False`
   - do not decode;
   - report missing composite;
   - request Maximize Compatibility or later Photoshop fallback.
3. `VERSION_INFO` absent
   - decode merged data when available;
   - mark unverified;
   - return an explicit warning.
4. Decoded dimensions differ from the document canvas
   - reject the image;
   - return an invalid-composite error.
5. Decode fails or returns `None`
   - return a user-readable error;
   - never fall back to layer rendering.

## Verified fixtures

Both real fixtures report:

- source: `embedded_merged`;
- reliable: yes;
- RGB, 8-bit;
- decoded mode: RGBA;
- alpha present;
- no embedded ICC profile;
- dimensions equal the canvas;
- first-slice pixels equal the Stage 0 baseline.

## Tests

Coverage includes:

- real PSD V8 composite;
- real PSB V6 composite;
- embedded ICC byte preservation;
- proof that `apply_icc=False` is used;
- proof that layer compositing is never called;
- explicit missing composite;
- absent VERSION_INFO;
- dimension mismatch;
- corrupt merged-channel decode;
- all Stage 0 and Stage 1 regressions.

Result:

```text
23 passed
```

## Stage 3 entry conditions

Stage 3 may build an original-size folder export service that:

- consumes `SliceParseResult` and `CompositeResult`;
- refuses unavailable or unreliable composites unless explicitly allowed;
- creates a collision-safe new output directory;
- exports only files from the current run;
- defaults to folder output with ZIP disabled;
- reports progress and supports cancellation between slices;
- reopens every written image and returns structured results.
