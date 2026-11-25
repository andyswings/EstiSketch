$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Push-Location $ProjectRoot
try {
    $BuildRoot = Join-Path $env:TEMP "es-win-bld"
    $StageSrc = Join-Path $BuildRoot "src"
    # Keep conda-build output in a sibling path that does not share $StageSrc as a string prefix.
    $env:CONDA_BLD_PATH = Join-Path $BuildRoot "cb"
    $env:CONDA_REPORT_ERRORS = "false"
    $ConstructorDir = Join-Path $BuildRoot "ctor"
    $DistDir = Join-Path $ProjectRoot "dist"

    if (Test-Path $BuildRoot) {
        Remove-Item -Recurse -Force $BuildRoot
    }
    New-Item -ItemType Directory -Force -Path $StageSrc, $env:CONDA_BLD_PATH, $ConstructorDir, $DistDir | Out-Null

    Write-Host "Staging clean source tree into $StageSrc..."
    foreach ($File in @("pyproject.toml", "setup.py", "LICENSE.txt", "README.md")) {
        $SrcFile = Join-Path $ProjectRoot $File
        if (Test-Path $SrcFile) {
            Copy-Item -Path $SrcFile -Destination (Join-Path $StageSrc $File)
        }
    }
    foreach ($Dir in @("src", "menu", "packaging", "conda-recipe")) {
        $SrcDir = Join-Path $ProjectRoot $Dir
        if (Test-Path $SrcDir) {
            Copy-Item -Recurse -Path $SrcDir -Destination (Join-Path $StageSrc $Dir)
        }
    }
    Get-ChildItem -Path $StageSrc -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    Get-ChildItem -Path $StageSrc -Recurse -File -Filter "*.py[cod]" | Remove-Item -Force -ErrorAction SilentlyContinue

    Write-Host "Building EstiSketch conda package into $env:CONDA_BLD_PATH..."
    conda build (Join-Path $StageSrc "conda-recipe") --python 3.12 --no-anaconda-upload --override-channels -c conda-forge
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
    Get-ChildItem -Path $DistDir -Filter "*.exe" | ForEach-Object {
        $SizeMb = [math]::Round($_.Length / 1MB, 2)
        Write-Host "  $($_.FullName) ($SizeMb MB)"
    }
}
finally {
    Pop-Location
}
