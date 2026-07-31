# Stage 10 - Final Release Acceptance

## Decision

Version 0.1.0 is accepted for Windows x64 delivery.

Supported artifact:

```text
release\PSD-PSB-Slice-Exporter-Windows-x64-v0.1.0.zip
```

Users must extract the archive before running the application and keep the EXE
beside its `_internal` directory.

## Acceptance matrix

| Area | Evidence | Result |
| --- | --- | --- |
| PSD parsing | pinned V8 fixture, 14 slices | accepted |
| PSB parsing | pinned V6 fixture, 14 slices | accepted |
| Requested width | extracted ZIP exported at 1,440px | accepted |
| Alternate width | packaged PSD and PSB exported at 750px | accepted |
| Pixel/output validation | all three packaged runs passed | accepted |
| Source protection | original hashes unchanged | accepted |
| Desktop launch | final EXE responding, clean exit | accepted |
| Drag-and-drop runtime | packaged Tcl extension 2.10.1 loaded | accepted |
| Photoshop bridge packaging | COM imports available | accepted |
| Automated regression | 136 passed, 1 opt-in GUI test skipped | accepted |
| Release archive | extracted 1,192 files and reran successfully | accepted |

The opt-in source-tree GUI test was covered by a direct launch of the exact
packaged application rather than by the pytest process.

## Release identity

```text
Product version: 0.1.0
Archive size: 35,248,737 bytes
```

Archive SHA-256:

```text
20E4DFAE68F6743CFE72D85DAA0CA70EE255F869DCAD3D70C76AA97FBFE1FB3A
```

Verification command:

```powershell
Get-FileHash -Algorithm SHA256 `
  .\release\PSD-PSB-Slice-Exporter-Windows-x64-v0.1.0.zip
```

## Fixture integrity

The acceptance run did not open Photoshop and did not modify either original
file:

```text
565656未标题-1.psd
29D9F690872FAE2013ED4FDD7AEB0BECBA01245B7E15DCEF0FFD0BF19121A7D0

详情切片.psb
E7B23A21574A3F5F442921C39A7AD5A9DAD68D8746001F4277CDA82B524AE288
```

## Operational constraints

- The version 0.1.0 package is an unsigned Windows x64 application.
- The extracted `_internal` directory is required; moving only the EXE breaks
  the application.
- Embedded-composite export is the default and does not require Photoshop.
- Photoshop fallback requires a compatible local Photoshop installation and
  follows the one-run permissions shown in the UI.
- The application creates collision-safe output directories instead of
  overwriting an earlier export.

## Handoff

The ZIP is the user-facing deliverable. `README-CN.txt` inside the extracted
folder contains the short Chinese operating guide. Build and acceptance details
remain in `docs/stage-9-report.md` and this report.
