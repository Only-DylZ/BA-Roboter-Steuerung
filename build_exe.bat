@echo off
title Pick & Place GUI - EXE Build
echo ================================================================
echo  Build: Pick ^& Place GUI   -   PyInstaller
echo ================================================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo FEHLER: Python nicht gefunden.
    pause & exit /b 1
)

pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installiere PyInstaller ...
    pip install pyinstaller
)

echo Baue EXE (onefile, windowed) ...
echo.

pyinstaller --onefile --windowed --name "PickAndPlace" --clean pick_and_place_gui_v2.py

echo.
if exist "dist\PickAndPlace.exe" (
    echo ================================================================
    echo  ERFOLG:  dist\PickAndPlace.exe
    echo ================================================================
) else (
    echo FEHLER: EXE nicht erstellt - Fehlermeldungen oben pruefen.
)
echo.
pause
