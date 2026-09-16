param(
    [string]$PythonCommand = "python"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = Join-Path $projectRoot "src"

Push-Location $projectRoot
try {
    & $PythonCommand -m mealcraft_data.cli run `
        --input data/fixtures/recipenlg_demo.csv `
        --sample-size 20 `
        --seed 5105 `
        --review-limit 200
    if ($LASTEXITCODE -ne 0) { throw "Cleaning pipeline failed." }

    & $PythonCommand -m mealcraft_data.cli validate `
        --recipes data/curated/recipes.jsonl `
        --ingredients data/curated/ingredients.jsonl
    if ($LASTEXITCODE -ne 0) { throw "Output validation failed." }

    $foodOn = Join-Path $projectRoot "data/reference/downloads/foodon-synonyms.tsv"
    if (Test-Path -LiteralPath $foodOn) {
        & $PythonCommand -m mealcraft_data.cli match-foodon `
            --ingredients data/curated/ingredients.jsonl
        if ($LASTEXITCODE -ne 0) { throw "FoodOn candidate matching failed." }
    }

    $usda = Join-Path $projectRoot "data/reference/downloads/usda-foundation-2026-04-30"
    if (Test-Path -LiteralPath $usda) {
        & $PythonCommand -m mealcraft_data.cli match-usda-foundation `
            --ingredients data/curated/ingredients.jsonl
        if ($LASTEXITCODE -ne 0) { throw "USDA candidate matching failed." }
    }

    & $PythonCommand -m unittest discover -s tests -v
    if ($LASTEXITCODE -ne 0) { throw "Tests failed." }

    Write-Host "Demo completed. Open reports/latest.md and data/review/." -ForegroundColor Green
}
finally {
    Pop-Location
}

