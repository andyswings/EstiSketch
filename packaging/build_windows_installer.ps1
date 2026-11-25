$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Push-Location $ProjectRoot
try {
    $ParentDir = Split-Path -Parent $ProjectRoot
    # Keep conda-build output outside $ProjectRoot so `source: path: ..` never copies into itself.
    $env:CONDA_BLD_PATH = Join-Path $ParentDir "estisketch-conda-bld"
    $ConstructorDir = Join-Path $ParentDir "estisketch-constructor"
    $DistDir = Join-Path $ProjectRoot "dist"

    foreach ($Dir in @($env:CONDA_BLD_PATH, $ConstructorDir)) {
        if (Test-Path $Dir) {
            Remove-Item -Recurse -Force $Dir
        }
    }
    New-Item -ItemType Directory -Force -Path $env:CONDA_BLD_PATH | Out-Null
    New-Item -ItemType Directory -Force -Path $ConstructorDir | Out-Null
    New-Item -ItemType Directory -Force -Path $DistDir | Out-Null

    Write-Host "Building EstiSketch conda package into $env:CONDA_BLD_PATH..."
    conda build conda-recipe --python 3.12 --no-anaconda-upload -c conda-forge
    if ($LASTEXITCODE -ne 0) {
        throw "conda build failed with exit code $LASTEXITCODE"
    }

    $ChannelUri = ([System.Uri]$env:CONDA_BLD_PATH).AbsoluteUri
    Write-Host "Staging Constructor config with local channel $ChannelUri..."
    Copy-Item (Join-Path $ProjectRoot "LICENSE.txt") (Join-Path $ConstructorDir "LICENSE.txt")
    $ConstructYaml = (Get-Content -Raw (Join-Path $ProjectRoot "construct.yaml")).Replace("../estisketch-conda-bld", $ChannelUri)
    [System.IO.File]::WriteAllText((Join-Path $ConstructorDir "construct.yaml"), $ConstructYaml, (New-Object System.Text.UTF8Encoding($false)))

    Write-Host "Building Windows installer (.exe) into $DistDir..."
    constructor "$ConstructorDir" --output-dir "$DistDir"
    if ($LASTEXITCODE -ne 0) {
        throw "constructor failed with exit code $LASTEXITCODE"
    }

    Write-Host "Windows installer build complete:"
    Get-ChildItem -Path $DistDir -Filter "*.exe" | ForEach-Object { Write-Host "  $($_.FullName)" }
}
finally {
    Pop-Location
}
