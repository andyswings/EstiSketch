@echo off
REM Post-install script for EstiSketch
echo Installing EstiSketch...

REM Download source from GitHub
echo Downloading EstiSketch source from GitHub...
powershell -NoProfile -ExecutionPolicy Bypass -Command "& {Invoke-WebRequest -Uri 'https://github.com/andyswings/EstiSketch/archive/refs/heads/main.zip' -OutFile '%PREFIX%\estisketch-source.zip'}"

if errorlevel 1 (
    echo Warning: Failed to download source from GitHub
    echo EstiSketch will still work, but source code is not available
    goto :skip_extract
)

REM Extract the downloaded source
echo Extracting EstiSketch source...
powershell -NoProfile -ExecutionPolicy Bypass -Command "& {Expand-Archive -LiteralPath '%PREFIX%\estisketch-source.zip' -DestinationPath '%PREFIX%' -Force}"

if errorlevel 1 (
    echo Warning: Failed to extract source
    goto :skip_extract
)

REM Rename the extracted folder
ren "%PREFIX%\EstiSketch-main" "estisketch-source"

REM Clean up zip file
del "%PREFIX%\estisketch-source.zip"

echo Source files downloaded to: %PREFIX%\estisketch-source
goto :end

:skip_extract
echo Continuing installation without source files...

:end
echo EstiSketch installed successfully!
exit /b 0
