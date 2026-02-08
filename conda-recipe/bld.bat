@echo off
REM Windows build script for EstiSketch conda package

python -m pip install . --no-deps --ignore-installed -vv
if errorlevel 1 exit 1
