# Stage 8 - Responsive Windows Desktop UI

## Status

Stage 8 is complete. The exporter now has a CustomTkinter desktop interface
with drag-and-drop, a persistent background worker, reusable parsed-document
sessions, settings persistence, progress reporting, and safe cancellation.

## Desktop entry points

```powershell
python -m app.main
python scripts/run_gui.py
```

Runtime UI dependencies:

```text
customtkinter==6.0.0
tkinterdnd2==0.6.2
```

`tkinterdnd2` is loaded into the existing CustomTkinter Tcl interpreter. If
the local Tk build cannot load the extension, the file chooser remains
available.

## Thread and ownership model

```text
Tk main thread
  -> immutable command
  -> command Queue
  -> one persistent non-daemon worker
       -> PreparedDocument
       -> full PIL composite
       -> PSD parsing / Photoshop COM / resize / encode / validate / ZIP
  -> immutable event
  -> event Queue
  -> Tk after(50 ms) event pump
```

The worker is the sole owner of `PreparedDocument` and the complete composite
image. The Tk thread receives only:

- immutable document metadata;
- normalized `SliceInfo` records;
- a bounded PNG preview;
- structured progress, result, cancellation, and failure events.

Loading another file closes the old image on the worker. Window shutdown sends
a cancellation request, queues worker shutdown, and polls for completion
without blocking the Tk event loop.

## Reusable prepared-document session

One successful load caches:

- normalized V6/V7/V8 slice data;
- decoded embedded or Photoshop composite;
- source SHA-256, size, and nanosecond modification time;
- the Photoshop fallback mode used for preparation.

Changing width, selection, format, color policy, naming, or output directory
reuses the cached document. A source fingerprint is recomputed immediately
before each export. If the PSD/PSB changed outside the application, export
stops and asks the user to reload.

Changing Photoshop fallback mode automatically reloads the document when the
cached composite is not compatible with the requested mode.

## UI features

- PSD/PSB file chooser and Windows file drag-and-drop;
- document canvas, color mode, bit depth, alpha, composite source, and slice
  count;
- bounded first-slice preview;
- selectable slice rows with coordinates, source dimensions, and live target
  dimensions;
- select all / select none;
- original width or positive custom width;
- optional no-upscale enforcement;
- PNG or JPEG, JPEG quality and background color;
- automatic, preserve-profile, or sRGB color policy;
- sequence/dimensions and slice-name naming rules;
- Photoshop fallback mode and one-run launch permission;
- explicit one-document permissions for unverified composites and mode
  conversion;
- custom output directory, optional ZIP, and open-on-complete;
- determinate per-slice progress plus indeterminate preparation phases;
- cancellation, output-folder access, and validation-report access.

Settings are stored as versioned JSON at:

```text
%APPDATA%\PSD Slice Exporter\settings.json
```

Writes use a same-directory temporary file, flush and `fsync`, followed by
atomic `os.replace`. Invalid JSON, unsupported schema versions, and invalid
individual fields recover safely. Photoshop launch, mode conversion, and
unverified-composite permissions are deliberately never persisted.

## Naming rules

The desktop defaults to the execution-plan format:

```text
01_1440x2000.png
02_1440x1876.png
```

Other UI choices:

```text
hero_1440x2000.png
01_hero_1440x2000.png
```

Windows-invalid characters, trailing dots/spaces, reserved device names, and
duplicate output names are handled safely. The existing service and CLI
default remains `slice_01_...` for backwards compatibility.

## Progress and cancellation

Early phases are now explicit:

```text
preparing
parsing
reading_composite
photoshop
resizing
starting
exporting
written
validating
archiving
```

Cancellation is checked:

- before PSD parsing;
- after slice parsing;
- after composite decoding;
- before and after Photoshop fallback;
- before and after full-canvas resize;
- between slice writes;
- between output validation checks;
- between ZIP entries.

PSD decoding, a single Photoshop COM call, one Pillow resize, and an in-flight
image encode cannot be interrupted inside the third-party call. The UI changes
to “safe cancellation” immediately and stops after that operation returns.
Completed files are kept and reported instead of being deleted.

## Verification

Deterministic coverage includes:

- versioned settings round trips and field-level recovery;
- atomic-save failure preservation;
- persistent non-daemon worker and task IDs;
- direct Event cancellation without command-queue delay;
- session replacement and shutdown image close;
- structured failure traceback;
- repeated cached exports without reparsing;
- stale source-fingerprint rejection;
- fallback-mode compatibility;
- preview-byte generation;
- form validation and live global scale estimates;
- naming rules and Windows filename sanitization;
- all previous parser, composite, resize, encoding, validation, Photoshop, and
  legacy regressions.

A real Windows GUI smoke test loaded the 1440 x 28164 PSD, displayed 14 slice
rows, recalculated every row at 750px, exported 14 files through the cached
worker session, and shut down the worker cleanly.

Final Stage 8 result across the parallel deterministic groups and the enabled
real GUI smoke test:

```text
135 passed
```

The Windows Computer Use screenshot provider could target the running Tk
window but returned system error `0x80004002` while capturing it. No blind UI
input was attempted; layout and behavior were verified through the real Tk
event loop smoke test instead.

## Stage 9 entry conditions

Packaging can now proceed with:

- a dedicated clean release virtual environment;
- PyInstaller onedir output first;
- CustomTkinter and tkinterdnd2 data/binary collection;
- a windowed entry point;
- packaged PSD/PSB smoke tests;
- onefile evaluation only after onedir is stable.
