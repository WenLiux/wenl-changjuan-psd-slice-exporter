$ErrorActionPreference = 'Stop'

$downloads = Join-Path $env:USERPROFILE 'Downloads'

if (-not $env:PSD_SLICE_V8_FIXTURE) {
    $fixture = Get-ChildItem -LiteralPath $downloads -Filter '*.psd' |
        Where-Object Length -EQ 135745016 |
        Select-Object -First 1
    if ($fixture) {
        $env:PSD_SLICE_V8_FIXTURE = $fixture.FullName
    }
}

if (-not $env:PSD_SLICE_V6_FIXTURE) {
    $fixture = Get-ChildItem -LiteralPath $downloads -Filter '*.psb' |
        Where-Object Length -EQ 142684479 |
        Select-Object -First 1
    if ($fixture) {
        $env:PSD_SLICE_V6_FIXTURE = $fixture.FullName
    }
}

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'

if (-not (Test-Path -LiteralPath $python)) {
    throw "Virtual environment not found: $python"
}

& $python -m pytest
exit $LASTEXITCODE
