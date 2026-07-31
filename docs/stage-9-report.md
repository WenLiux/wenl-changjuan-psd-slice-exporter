# Stage 9 - Windows Packaging and Packaged-App Verification

## Status

Stage 9 is complete. Version 0.1.0 is available as a 64-bit Windows onedir
application and as a distributable ZIP containing the complete application
folder.

## Reproducible build

The release environment used:

```text
Python 3.12.13
PyInstaller 6.21.0
customtkinter 6.0.0
tkinterdnd2 0.6.2
pywin32 311
```

Build dependencies are pinned through `requirements-build.txt`. The build
entry point is:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\build_windows.ps1
```

The PyInstaller specification:

- builds a windowed, non-console executable;
- collects CustomTkinter themes and tkinterdnd2 Tcl binaries;
- includes the Python COM and win32com modules used by Photoshop fallback;
- embeds version 0.1.0 Windows file metadata;
- disables UPX to avoid an undeclared external compressor dependency;
- produces onedir output before any onefile experiment.

The Chinese end-user guide is copied beside the executable after every build.

## Release artifacts

Application directory:

```text
dist\PSD-PSB-Slice-Exporter
```

Distributable archive:

```text
release\PSD-PSB-Slice-Exporter-Windows-x64-v0.1.0.zip
```

Final sizes:

```text
Application folder: 1,192 files, 84,970,332 bytes
ZIP archive:         35,248,737 bytes
Executable:           6,400,599 bytes
```

SHA-256:

```text
ZIP:
20E4DFAE68F6743CFE72D85DAA0CA70EE255F869DCAD3D70C76AA97FBFE1FB3A

EXE:
33BD0E1CF6E9BA81C1A5343E69555E53F24412488894CB2C4E3BDE7047213CB3
```

The EXE is not standalone. `_internal` must remain beside it, so the ZIP is the
recommended deliverable.

## Packaged verification

The exact final build was exercised without opening Photoshop:

| Input | Width | Slices | Validation | Source unchanged | Result |
| --- | ---: | ---: | --- | --- | --- |
| pinned V8 PSD | 750 | 14 | passed | yes | passed |
| pinned V6 PSB | 750 | 14 | passed | yes | passed |

Both runs also confirmed:

- `sys.frozen` was true;
- Python COM, pywintypes, and win32com imports were available;
- the packaged tkinterdnd2 Tcl extension loaded as version 2.10.1;
- normal embedded-composite export completed without Photoshop fallback.

The final windowed EXE then launched as a responding Windows application with
the title `PSD / PSB 高保真切片导出器` and closed normally with exit code 0.

## ZIP extraction verification

The distributable ZIP was expanded into a clean verification directory. The
expanded package contained all 1,192 expected files. Its EXE exported the
pinned PSD at the requested 1,440px width:

```text
status: completed
slices: 14
validation: passed
source unchanged: yes
tkinterdnd2: 2.10.1
```

This proves the shipped archive, not only the local build directory, contains
the required runtime data and binaries.

## Source regression

The deterministic and real-fixture suite collected 137 tests:

```text
136 passed, 1 skipped
```

The single skip is the opt-in source-tree GUI smoke test. The exact packaged
GUI was launched and checked separately as described above.

The two original fixture hashes remained:

```text
565656未标题-1.psd
29D9F690872FAE2013ED4FDD7AEB0BECBA01245B7E15DCEF0FFD0BF19121A7D0

详情切片.psb
E7B23A21574A3F5F442921C39A7AD5A9DAD68D8746001F4277CDA82B524AE288
```

## Onefile decision

The verified onedir folder, delivered as one ZIP, is the version 0.1.0 release
format. A onefile build is deferred: it would still unpack its runtime payload
at launch and would add another artifact that needs the complete PSD, PSB,
drag-and-drop, COM, and GUI matrix. The onedir ZIP already gives users a single
download while keeping startup and packaged-data behavior explicit.

## Stage 10 entry conditions

Final acceptance can now:

- audit the committed Stage 9 changes;
- verify the repository is clean;
- confirm the release hash and user instructions;
- hand off the ZIP as the supported Windows artifact.
