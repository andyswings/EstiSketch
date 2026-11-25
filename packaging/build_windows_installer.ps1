$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Push-Location $ProjectRoot
try {
    $env:CONDA_BLD_PATH = Join-Path $ProjectRoot "conda-bld"
    $DistDir = Join-Path $ProjectRoot "dist"
    New-Item -ItemType Directory -Force -Path $env:CONDA_BLD_PATH | Out-Null
    New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

    Write-Host "Building EstiSketch conda package into $env:CONDA_BLD_PATH..."
    conda build conda-recipe --python 3.12 --no-anaconda-upload -c conda-forge
    if ($LASTEXITCODE -ne 0) {
        throw "conda build failed with exit code $LASTEXITCODE"
    }

    Write-Host "Building Windows installer (.exe) into $DistDir..."
    constructor . --output-dir "$DistDir"
    if ($LASTEXITCODE -ne 0) {
        throw "constructor failed with exit code $LASTEXITCODE"
    }

    Write-Host "Windows installer build complete:"
    Get-ChildItem -Path $DistDir -Filter "*.exe" | ForEach-Object { Write-Host "  $($_.FullName)" }
}
finally {
    Pop-Location
}
