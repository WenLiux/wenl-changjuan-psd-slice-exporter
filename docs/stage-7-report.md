# Stage 7 - Photoshop High-Fidelity Fallback

## Status

Stage 7 is complete. Photoshop fallback is an explicit, optional composite
source for 8-bit RGB PSD/PSB files. The embedded merged image remains the
default and never starts Photoshop.

## Added module

```text
app/core/photoshop_bridge.py
```

Optional Windows dependency:

```text
requirements-photoshop.txt
pyproject.toml [project.optional-dependencies].photoshop
```

## Selection modes

`ExportOptions.photoshop_fallback` accepts:

```text
disabled
if_needed
always
```

Behavior:

| Mode | Result |
| --- | --- |
| `disabled` | Use only the embedded Photoshop-saved composite |
| `if_needed` | Use Photoshop only when the embedded composite is missing or cannot be verified |
| `always` | Explicitly render the temporary copy with Photoshop |

Fallback is disabled by default. Photoshop launch is a second, separate
permission and is also disabled by default.

`ExportResult` records both the actual `composite_source` and a user-readable
fallback reason.

## Source-protection workflow

```text
hash original PSD/PSB
  -> copy it to a unique system temporary directory
  -> verify copied bytes against the original hash
  -> attach to Photoshop through COM
  -> require zero pre-existing user documents
  -> suppress dialogs temporarily
  -> open only the temporary source copy
  -> standard PNG Save As Copy
  -> reopen and validate the PNG
  -> close only the owned temporary document without saving
  -> restore the original Photoshop dialog mode
  -> verify the Photoshop document-ID set is unchanged
  -> delete the temporary directory
  -> hash the original PSD/PSB again
```

The bridge never passes the original source path to Photoshop.

The original fingerprint contains:

- SHA-256;
- byte length;
- nanosecond modification time.

Any difference aborts the run with a source-integrity error.

## Photoshop automation boundary

The adapter uses Photoshop's standard PNG `SaveAs`, not Save for Web. It does
not flatten the document, merge layers, resize the canvas, change preferences,
save the temporary PSD/PSB, or modify the original.

Ownership rules:

- no user document may be open when fallback starts;
- document ownership is tracked by Photoshop document ID;
- only the temporary document opened by the current run is closed;
- every close uses `DoNotSaveChanges`;
- the application's original dialog mode is restored in `finally`;
- `Application.Quit()` is never called;
- an application launched with explicit permission is left running.

All COM activity initializes and releases its own apartment on the calling
thread. The future UI worker must keep these calls on that worker thread and
must not pass COM proxies to the Tk main thread.

## Output checks

Before the Photoshop PNG becomes a `CompositeResult`, the bridge verifies:

- file exists and is non-empty;
- Pillow can reopen and fully decode it;
- format is PNG;
- dimensions equal the PSD/PSB canvas;
- mode is RGB or RGBA;
- a source transparency channel was not dropped.

The actual PNG ICC is retained. If Photoshop omits the PNG ICC but the PSD/PSB
contains one, the source ICC bytes are carried forward so the normal Stage 6
encoder can embed them in final slices.

V1 deliberately rejects CMYK, non-RGB, and non-8-bit Photoshop fallback. Those
documents receive a specific message and are not silently converted.

## CLI examples

Install the optional bridge:

```powershell
python -m pip install -r requirements-photoshop.txt
```

Use Photoshop only when required:

```powershell
python scripts/export_slices.py input.psb --photoshop if_needed
```

Force a high-fidelity Photoshop render:

```powershell
python scripts/export_slices.py input.psd --photoshop always
```

Permit Photoshop to start when it is not already running:

```powershell
python scripts/export_slices.py input.psd --photoshop always `
  --allow-photoshop-launch
```

For the default attach-only path, Photoshop must already be running with no
open documents.

## Real Photoshop 2025 verification

Environment:

```text
Adobe Photoshop 2025
Version 26.7.0
pywin32 311
```

Temporary-composite smoke tests:

| Fixture | Canvas | Output | Alpha | Time | Source unchanged |
| --- | ---: | --- | --- | ---: | --- |
| PSD V8 | 1440 x 28164 | RGBA PNG | Preserved | 9.828 s | Yes |
| PSB V6 | 1440 x 31044 | RGBA PNG | Preserved | 9.474 s | Yes |

After both runs, Photoshop contained zero open documents.

Source fingerprints before and after every live run were identical:

| Fixture | Bytes | mtime_ns | SHA-256 |
| --- | ---: | ---: | --- |
| PSD | 135745016 | 1785460619817393300 | `29d9f690872fae2013ed4fdd7aeb0becba01245b7e15dcef0ffd0bf19121a7d0` |
| PSB | 142684479 | 1785461236819932800 | `e7b23a21574a3f5f442921c39a7ad5a9dad68d8746001f4277cda82b524ae288` |

Both Photoshop PNGs were compared against the Photoshop-saved embedded
composites. Alpha is checked independently; RGB differences are counted only
where alpha is greater than zero.

PSD, 40,556,160 pixels:

- alpha differences: 0 pixels;
- visible RGB differences: 23,938 pixels, about 0.0590%;
- maximum visible RGB difference: 1 level out of 255.

PSB, 44,703,360 pixels:

- alpha differences: 0 pixels;
- visible RGB differences: 23,938 pixels, about 0.0535%;
- maximum visible RGB difference: 1 level out of 255;
- maximum alpha difference: 0.

The one-level RGB difference is retained as an observed Photoshop-versus-PNG
rounding characteristic. The normal embedded-composite path remains the exact
pixel path whenever it is available.

End-to-end forced fallback on the PSD:

- Photoshop temporary render;
- 14 original-size PNG slices;
- 14 files reopened and validated;
- validation errors: 0;
- validation warnings: 0;
- source unchanged: yes;
- total time: 17.820 seconds.

## Automated tests

New deterministic coverage includes:

- temporary-copy byte equality and cleanup;
- source SHA/size/time preservation;
- intentional source-change detection;
- 8-bit RGB scope enforcement;
- rendered-format, dimensions, mode, and alpha validation;
- source ICC carry-forward when Photoshop omits PNG profile metadata;
- temporary-cleanup failure reporting without hiding the render error;
- COM attach-only default;
- separate launch permission;
- refusal when a saved or unsaved user document is open;
- exact document-ID ownership checks;
- dialog-mode restoration;
- cleanup after Save As failure;
- close-without-save behavior;
- proof that `Application.Quit()` is never called;
- `disabled`, `if_needed`, and `always` service routing;
- reliable embedded composite bypass;
- all Stage 0 through Stage 6 regressions.

Result:

```text
65 passed
```

## Stage 8 entry conditions

The desktop UI can now expose:

- embedded versus Photoshop composite source;
- explicit fallback mode and launch permission;
- a prompt to save and close Photoshop documents;
- user-readable automation and integrity errors;
- Photoshop work on the existing export worker thread.

Before UI work, the service should add earlier `preparing` progress events and
additional cancellation checks around parsing, composite decoding, and ZIP
startup.
