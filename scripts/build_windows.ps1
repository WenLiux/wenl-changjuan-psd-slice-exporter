param(
    [string]$PythonPath = (
        Join-Path $PSScriptRoot "..\.venv-release\Scripts\python.exe"
    )
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$resolvedPython = (Resolve-Path $PythonPath).Path
$specPath = Join-Path $projectRoot "packaging\psd_slice_exporter.spec"

Push-Location $projectRoot
try {
    & $resolvedPython -m PyInstaller `
        --clean `
        --noconfirm `
        $specPath
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }
}
finally {
    Pop-Location
}

$executable = Join-Path $projectRoot (
    "dist\PSD-PSB-Slice-Exporter\PSD-PSB-Slice-Exporter.exe"
)
if (-not (Test-Path -LiteralPath $executable -PathType Leaf)) {
    throw "Packaged executable was not created: $executable"
}
$readmeSource = Join-Path $projectRoot "packaging\README-CN.txt"
$readmeTarget = Join-Path (
    Split-Path -Parent $executable
) "README-CN.txt"
Copy-Item -LiteralPath $readmeSource -Destination $readmeTarget -Force
Write-Output $executable
