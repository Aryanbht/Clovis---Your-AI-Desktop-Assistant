@echo off
title Clovis -- Text Mode

rem -- Point to the venv Python directly ---------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  [ERROR] Virtual environment not found.
    echo  Please run install.bat first.
    echo.
    pause
    exit /b 1
)

set "PYTHON=%~dp0.venv\Scripts\python.exe"
set PYTHONIOENCODING=utf-8

rem -- Auto-start Ollama if installed but not running --------------------------
ollama --version >nul 2>&1
if not errorlevel 1 (
    ollama list >nul 2>&1
    if errorlevel 1 (
        echo  Starting Ollama in background...
        start "" /B ollama serve
        timeout /t 3 /nobreak >nul
    )
)

echo.
echo  Starting Clovis in text mode (no microphone needed)...
echo  Type your commands and press Enter. Type 'bye' to exit.
echo.

"%PYTHON%" "%~dp0main.py" --text %*
