@echo off
REM FailFixer – PyInstaller build script
REM Run from the failfixer/ project root

echo === FailFixer Build ===

REM Install deps if needed
pip install -r requirements.txt pyinstaller

REM Extract version from __init__.py (e.g. "v0.2.0-beta")
for /f "usebackq tokens=*" %%V in (`python get_version.py`) do set FF_VERSION=%%V

if "%FF_VERSION%"=="" (
    echo WARNING: Could not read version, falling back to "dev"
    set FF_VERSION=dev
)

echo Building FailFixer %FF_VERSION%...

REM Build single-file executable with version in filename
pyinstaller --onefile --windowed ^
    --icon=assets\logo.ico ^
    --add-data "assets;assets" ^
    --add-data "profiles;profiles" ^
    --name FailFixer_%FF_VERSION% ^
    run_gui.py

REM Also copy to stable filename for convenience
if exist "dist\FailFixer_%FF_VERSION%.exe" (
    copy /Y "dist\FailFixer_%FF_VERSION%.exe" "dist\FailFixer.exe" >nul
)

echo.
echo Build complete. Outputs:
echo   dist\FailFixer_%FF_VERSION%.exe
echo   dist\FailFixer.exe
pause
