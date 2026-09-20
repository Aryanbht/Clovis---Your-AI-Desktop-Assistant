@echo off
setlocal EnableDelayedExpansion
title Clovis -- Setup

echo.
echo  ================================================
echo    Clovis Voice Assistant -- First-time Setup
echo  ================================================
echo.

rem -- 1. Check Python ----------------------------------------------------------
echo [1/5] Checking Python version...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERROR] Python not found in PATH.
    echo  Please install Python 3.10 or later from https://www.python.org/downloads/
    echo  Make sure to check "Add Python to PATH" during installation.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PY_VER=%%v
for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)
if !PY_MAJOR! LSS 3 (
    echo  [ERROR] Python 3.10+ required. Found !PY_VER!
    pause
    exit /b 1
)
if !PY_MAJOR! EQU 3 if !PY_MINOR! LSS 10 (
    echo  [ERROR] Python 3.10+ required. Found !PY_VER!
    pause
    exit /b 1
)
echo  [OK] Python !PY_VER! found.


rem -- 2. Create virtual environment --------------------------------------------
echo.
echo [2/5] Creating virtual environment (.venv)...
if exist ".venv" (
    echo  [SKIP] .venv already exists.
) else (
    python -m venv .venv
    if errorlevel 1 (
        echo  [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo  [OK] .venv created.
)


rem -- 3. Install Python dependencies -------------------------------------------
echo.
echo [3/5] Installing Python dependencies (this may take a few minutes)...
call ".venv\Scripts\activate.bat"
set PYTHONIOENCODING=utf-8
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt
if errorlevel 1 (
    echo  [ERROR] Dependency installation failed. Check the output above.
    pause
    exit /b 1
)
echo  [OK] All Python packages installed.


rem -- 4. Check Ollama ----------------------------------------------------------
echo.
echo [4/5] Checking Ollama...
ollama --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [WARNING] Ollama not found.
    echo  Clovis will still run in text mode, but LLM features need Ollama.
    echo  Install from: https://ollama.com
    echo.
    goto skip_model
)
echo  [OK] Ollama found.


rem -- 5. Pull LLM model --------------------------------------------------------
echo.
echo [5/5] Pulling Ollama model (qwen2.5:3b-instruct)...
echo  Note: This is about 2 GB and only downloads once.
echo  You can press Ctrl+C to skip and pull it later with:
echo    ollama pull qwen2.5:3b-instruct
echo.
ollama pull qwen2.5:3b-instruct
if errorlevel 1 (
    echo  [WARNING] Model pull failed. Run this later:
    echo    ollama pull qwen2.5:3b-instruct
) else (
    echo  [OK] Model ready.
)

:skip_model


rem -- Done ---------------------------------------------------------------------
echo.
echo  ================================================
echo    Setup complete!
echo.
echo    Open a NEW terminal and type:
echo.
echo      clovis
echo.
echo    That's it! Clovis will ask which mode you want.
echo  ================================================
echo.
pause
exit /b 0
