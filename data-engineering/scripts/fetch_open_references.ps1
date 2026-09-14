param(
    [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $projectRoot "src"

Push-Location $projectRoot
try {
    & $PythonCommand -m mealcraft_data.cli fetch-foodon
    if ($LASTEXITCODE -ne 0) { throw "FoodOn download failed." }

    & $PythonCommand -m mealcraft_data.cli fetch-usda-foundation
    if ($LASTEXITCODE -ne 0) { throw "USDA Foundation Foods download failed." }

    Write-Host "Open reference datasets downloaded with manifests." -ForegroundColor Green
}
finally {
    Pop-Location
}

