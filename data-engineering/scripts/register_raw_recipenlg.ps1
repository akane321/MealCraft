param(
    # Path to the downloaded RecipeNLG archive (the official dataset.zip). Optional
    # if full_dataset.csv has already been extracted into data/raw/recipenlg/.
    [string]$ArchivePath,
    # Skip the dataset.zip MD5 comparison. Required for any non-official mirror
    # (e.g. the Kaggle re-upload), whose packaging will not match the PUT hash.
    [switch]$SkipArchiveHash,
    # Where the data was actually obtained. Record the real URL you downloaded
    # from so provenance is honest (official site vs. Kaggle mirror vs. other).
    [string]$SourceUrl = "https://recipenlg.cs.put.poznan.pl/dataset",
    # Contributor role that accepted the RecipeNLG terms. The manifest is committed
    # to a public repository, so record a role, never a personal or OS user name.
    [string]$AcceptedBy = "dataset"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$rawDir      = Join-Path $projectRoot "data/raw/recipenlg"
$csvPath     = Join-Path $rawDir "full_dataset.csv"
$manifestPath = Join-Path $rawDir "raw_manifest.json"
$registryPath = Join-Path $rawDir "source_registry.json"

# Official RecipeNLG archive checksum, published on the dataset page for dataset.zip.
$expectedArchiveMd5 = "3A168DFD0912BB034225619B3586CE76"

$sourceUrl   = $SourceUrl
$sourceRepo  = "https://github.com/Glorf/recipenlg"

New-Item -ItemType Directory -Force -Path $rawDir | Out-Null

function Write-Utf8Json {
    param([Parameter(Mandatory)] $Object, [Parameter(Mandatory)] [string] $Path)
    $json = $Object | ConvertTo-Json -Depth 8
    [System.IO.File]::WriteAllText($Path, $json + "`n", (New-Object System.Text.UTF8Encoding($false)))
}

# --- 1. Optionally verify and extract the archive ------------------------------
$archiveInfo = $null
if ($ArchivePath) {
    if (-not (Test-Path -LiteralPath $ArchivePath)) {
        throw "Archive not found: $ArchivePath"
    }
    $archiveItem = Get-Item -LiteralPath $ArchivePath
    $md5 = (Get-FileHash -LiteralPath $ArchivePath -Algorithm MD5).Hash.ToUpperInvariant()
    $sha256Archive = (Get-FileHash -LiteralPath $ArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()

    Write-Host "Archive        : $ArchivePath"
    Write-Host "Archive bytes  : $($archiveItem.Length)"
    Write-Host "Archive MD5    : $md5"
    Write-Host "Expected MD5   : $expectedArchiveMd5"

    if ($md5 -ne $expectedArchiveMd5) {
        if ($SkipArchiveHash) {
            Write-Warning "MD5 mismatch, continuing because -SkipArchiveHash was set."
        } else {
            throw "dataset.zip MD5 mismatch. Re-download the archive or pass -SkipArchiveHash if you have independently verified it."
        }
    } else {
        Write-Host "Archive MD5 verified." -ForegroundColor Green
    }

    Write-Host "Extracting full_dataset.csv ..."
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($archiveItem.FullName)
    try {
        $entry = $zip.Entries | Where-Object { $_.Name -eq "full_dataset.csv" } | Select-Object -First 1
        if (-not $entry) { throw "full_dataset.csv not found inside the archive." }
        [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $csvPath, $true)
    }
    finally {
        $zip.Dispose()
    }

    $archiveInfo = [ordered]@{
        archive_path   = "data\raw\recipenlg\" + $archiveItem.Name
        archive_bytes  = $archiveItem.Length
        archive_md5    = $md5
        archive_sha256 = $sha256Archive
        archive_md5_expected = $expectedArchiveMd5
        archive_md5_verified = ($md5 -eq $expectedArchiveMd5)
    }
}

if (-not (Test-Path -LiteralPath $csvPath)) {
    throw "full_dataset.csv is not present. Either pass -ArchivePath <dataset.zip> or place full_dataset.csv into $rawDir manually."
}

# --- 2. Hash and profile full_dataset.csv -------------------------------------
Write-Host "Hashing full_dataset.csv (this can take a minute) ..."
$csvItem   = Get-Item -LiteralPath $csvPath
$csvSha256 = (Get-FileHash -LiteralPath $csvPath -Algorithm SHA256).Hash.ToLowerInvariant()

# Read just the header line for the record.
$reader = [System.IO.StreamReader]::new($csvPath)
try { $header = $reader.ReadLine() } finally { $reader.Dispose() }

# Accurate record count and source breakdown. Prefer a real CSV parse (quoted
# fields contain newlines); fall back to a raw line count if Python is missing.
$recordCount = $null
$countMethod = $null
$sourceCounts = $null
$python = Get-Command python -ErrorAction SilentlyContinue
if ($python) {
    $py = @"
import csv, sys, json, collections
csv.field_size_limit(10_000_000)
n = 0
by_source = collections.Counter()
with open(sys.argv[1], encoding='utf-8', newline='') as f:
    r = csv.DictReader(f)
    for row in r:
        n += 1
        by_source[row.get('source')] += 1
print(json.dumps({'records': n, 'by_source': dict(by_source)}))
"@
    try {
        $parsed = (& $python.Source -c $py $csvPath).Trim() | ConvertFrom-Json
        $recordCount = [int]$parsed.records
        $countMethod = "csv_parse"
        $sourceCounts = [ordered]@{}
        foreach ($p in $parsed.by_source.PSObject.Properties) { $sourceCounts[$p.Name] = $p.Value }
    } catch {
        Write-Warning "Python CSV profile failed ($_); falling back to line count."
    }
}
if ($null -eq $recordCount) {
    $lineCount = 0
    $reader = [System.IO.StreamReader]::new($csvPath)
    try { while ($null -ne $reader.ReadLine()) { $lineCount++ } }
    finally { $reader.Dispose() }
    $recordCount = $lineCount - 1
    $countMethod = "raw_line_count_may_overcount"
}

Write-Host "CSV bytes      : $($csvItem.Length)"
Write-Host "CSV SHA-256    : $csvSha256"
Write-Host "CSV records    : $recordCount ($countMethod)"
if ($sourceCounts) { Write-Host "By source      : $(($sourceCounts.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join ', ')" }
Write-Host "CSV header     : $header"

# --- 3. Write raw_manifest.json ---------------------------------------------
$manifest = [ordered]@{
    source          = "RecipeNLG"
    source_url      = $sourceUrl
    source_repo     = $sourceRepo
    source_license  = "Research and education, non-commercial only; terms accepted by downloader"
    terms_accepted_by = $AcceptedBy
    retrieved_at    = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    local_path      = "data\raw\recipenlg\full_dataset.csv"
    committed_to_git = $false
    file_bytes      = $csvItem.Length
    file_sha256     = $csvSha256
    record_count    = $recordCount
    record_count_method = $countMethod
    record_count_by_source = $sourceCounts
    csv_header      = $header
}
if ($archiveInfo) { $manifest.archive = $archiveInfo }

Write-Utf8Json -Object $manifest -Path $manifestPath
Write-Host "Wrote $manifestPath" -ForegroundColor Green

# --- 4. Write / refresh source_registry.json --------------------------------
$registry = [ordered]@{
    source_name           = "RecipeNLG"
    source_url            = $sourceUrl
    source_record_id     = "recipenlg-full_dataset.csv"
    source_license       = "Research/education, non-commercial. Some rows originate from Recipe1M+; the 'source' column must be preserved."
    retrieved_at         = $manifest.retrieved_at
    source_version       = "full_dataset.csv (single published release)"
    transformation_version = "mealcraft-data-cleaning/0.1.0"
    permitted_uses       = @(
        "Local parsing, NER cross-check, cleaning and sampling",
        "Derived curated records whose redistribution is permitted"
    )
    prohibited_uses      = @(
        "Committing the raw CSV or archive to any Git repository",
        "Commercial use",
        "Redistributing raw RecipeNLG rows through MealCraft"
    )
    raw_manifest         = "data\raw\recipenlg\raw_manifest.json"
}

Write-Utf8Json -Object $registry -Path $registryPath
Write-Host "Wrote $registryPath" -ForegroundColor Green

Write-Host ""
Write-Host "Raw source registered. Next: task #3 - run the fixed-seed 5,000-row profiling:" -ForegroundColor Cyan
Write-Host '  $env:PYTHONPATH = "$PWD/src"'
Write-Host '  python -m mealcraft_data.cli run --input data/raw/recipenlg/full_dataset.csv --sample-size 5000 --seed 5105 --source-filter Gathered --review-limit 200'
