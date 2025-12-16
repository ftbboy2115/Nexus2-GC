@echo off
TITLE Nexus Launcher
COLOR 0A

:: 1. Force path to current directory (Quoted to handle spaces and parentheses)
cd /d "%~dp0"

echo ===================================================
echo    NEXUS TRADING SYSTEM
echo ===================================================
echo.

:: 2. Check if Python exists in the local .venv folder
IF NOT EXIST ".venv\Scripts\python.exe" GOTO ErrorMissing

:: 3. Run directly using the virtual environment's Python
:: We use the full relative path to avoid "activate.bat" issues
echo [INFO] Launching System...
".venv\Scripts\python.exe" launcher.py

:: 4. Pause on exit so you can see any errors
echo.
echo [STOP] System halted.
pause
goto End

:ErrorMissing
COLOR 0C
echo [CRITICAL ERROR]
echo The file ".venv\Scripts\python.exe" was not found.
echo Please make sure this batch file is inside your 'Nexus' folder.
echo.
pause

:End