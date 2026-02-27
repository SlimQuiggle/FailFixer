@echo off
REM FailFixer – PyInstaller build script
REM Run from the failfixer/ project root

echo === FailFixer Build ===

REM Install deps if needed
pip install -r requirements.txt pyinstaller

REM Build single-file executable
pyinstaller --onefile --windowed ^
    --icon=assets\logo.ico ^
    --add-data "assets;assets" ^
    --add-data "profiles;profiles" ^
    --name FailFixer ^
    run_gui.py

echo.
echo Build complete. Output: dist\FailFixer.exe
pause
