@echo off
title JARVIS Installer
cd /d "%~dp0"
echo ========================================
echo   JARVIS Dependency Installer
echo ========================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 goto nopython

echo Python found. Installing libraries...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo [ERROR] Install failed. See message above.
    goto done
)
echo.
echo [OK] Libraries installed!
goto done

:nopython
echo Python is NOT installed!
echo.
echo Please install Python first:
echo   Go to https://www.python.org/downloads/
echo   Download Python 3.10 or newer
echo   IMPORTANT: Check "Add Python to PATH" during install
echo.
echo After installing, run this file again.
echo.
pause
exit

:done
echo.
echo ========================================
echo   Next steps:
echo   1. Install Ollama from https://ollama.com
echo   2. Run:  ollama pull llama3.2
echo   3. Double-click JARVIS_Control.bat
echo ========================================
echo.
cmd /k
