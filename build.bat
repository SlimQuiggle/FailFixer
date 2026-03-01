@echo off
REM FailFixer – PyInstaller build script
REM Run from the failfixer/ project root

echo === FailFixer Build ===

REM Install deps if needed
pip install -r requirements.txt pyinstaller

REM Extract version from __init__.py (e.g. "v0.2.1-beta")
for /f "usebackq tokens=*" %%V in (`python get_version.py`) do set FF_VERSION=%%V

if "%FF_VERSION%"=="" (
    echo WARNING: Could not read version, falling back to "dev"
    set FF_VERSION=dev
)

echo Building FailFixer %FF_VERSION%...

REM Build single-file executable with version in filename (no overwrite of prior versions)
pyinstaller --onefile --windowed ^
    --icon=assets\logo.ico ^
    --add-data "assets;assets" ^
    --add-data "profiles;profiles" ^
    --name FailFixer_%FF_VERSION% ^
    run_gui.py

echo.
echo Build complete. Output:
echo   dist\FailFixer_%FF_VERSION%.exe
pause
