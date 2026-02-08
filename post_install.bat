@echo off
REM Post-install script for EstiSketch
echo Installing EstiSketch...

REM Extract the source archive
echo Extracting EstiSketch source...
powershell -Command "Expand-Archive -Path '%PREFIX%\estisketch-source.zip' -DestinationPath '%PREFIX%' -Force"

if errorlevel 1 (
    echo Failed to extract EstiSketch source
    exit /b 1
)

REM Install EstiSketch using pip
echo Installing EstiSketch package...
"%PREFIX%\python.exe" -m pip install --no-deps --no-build-isolation "%PREFIX%"

if errorlevel 1 (
    echo Failed to install EstiSketch
    exit /b 1
)

echo EstiSketch installed successfully!
exit /b 0
