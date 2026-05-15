# Task runner for blender-captions.
# Usage: .\tasks.ps1 <task>
#   test-lint    -- Tier 1, no Blender, seconds
#   test-unit    -- Tier 2, pytest, no Blender, seconds
#   test-blender -- Tier 3, requires Blender, ~30s startup
#   test-all     -- run all three tiers in order, stop at first failure
#   build-zip    -- rebuild dist/captions_tool-VERSION.zip from current source

param([string]$Task = "test-all")

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
Set-Location $root

# Path to a Blender executable. Override via env var if it's somewhere else.
$blender = if ($env:BLENDER) { $env:BLENDER } else { "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" }

function Get-AddonVersion {
    $initPy = Get-Content "$root\captions_tool\__init__.py" -Raw
    if ($initPy -match '"version"\s*:\s*\((\d+),\s*(\d+),\s*(\d+)\)') {
        return "$($Matches[1]).$($Matches[2]).$($Matches[3])"
    }
    throw "Couldn't parse bl_info.version"
}

function Invoke-Lint {
    Write-Host "==> Tier 1: lint" -ForegroundColor Cyan
    python "$root\tests\lint\check.py"
    if ($LASTEXITCODE -ne 0) { throw "Tier 1 failed" }
}

function Invoke-Unit {
    Write-Host "==> Tier 2: pytest" -ForegroundColor Cyan
    python -m pytest "$root\tests\unit" -v
    if ($LASTEXITCODE -ne 0) { throw "Tier 2 failed" }
}

function Invoke-Blender {
    Write-Host "==> Tier 3: Blender integration" -ForegroundColor Cyan
    if (-not (Test-Path $blender)) {
        throw "Blender not found at $blender. Set `$env:BLENDER to override."
    }
    $env:BLCAP_REPO = $root
    & $blender --background --factory-startup --python "$root\tests\integration\run.py"
    if ($LASTEXITCODE -ne 0) { throw "Tier 3 failed" }
}

function Invoke-BuildZip {
    $version = Get-AddonVersion
    $zipPath = "$root\dist\captions_tool-$version.zip"
    $tmp = "$env:TEMP\captions_tool-$version.zip"
    Write-Host "==> Building $zipPath" -ForegroundColor Cyan
    Compress-Archive -Force -Path "$root\captions_tool" -DestinationPath $tmp
    Copy-Item -Force $tmp $zipPath
    Remove-Item $tmp
    Get-Item $zipPath | Select-Object Name, Length
}

switch ($Task) {
    "test-lint"    { Invoke-Lint }
    "test-unit"    { Invoke-Unit }
    "test-blender" { Invoke-Blender }
    "test-all"     { Invoke-Lint; Invoke-Unit; Invoke-Blender }
    "build-zip"    { Invoke-BuildZip }
    default        { Write-Error "Unknown task '$Task'. Try test-lint, test-unit, test-blender, test-all, build-zip." }
}
