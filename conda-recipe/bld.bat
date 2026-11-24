@echo off
REM Windows build script for EstiSketch conda package

python -m pip install . --no-deps --no-build-isolation --ignore-installed -vv
if errorlevel 1 exit 1

if not exist "%PREFIX%\Menu" mkdir "%PREFIX%\Menu"
if errorlevel 1 exit 1

copy /Y "menu\estisketch-menu.json" "%PREFIX%\Menu\estisketch-menu.json"
if errorlevel 1 exit 1

copy /Y "packaging\estisketch_128.png" "%PREFIX%\Menu\estisketch.png"
if errorlevel 1 exit 1

python "packaging\make_ico.py" "packaging\estisketch_128.png" "%PREFIX%\Menu\estisketch.ico"
if errorlevel 1 exit 1
