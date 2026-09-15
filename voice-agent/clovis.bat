@echo off
setlocal EnableDelayedExpansion

rem Change to the directory where this .bat file lives.
rem This ensures all relative paths (venv, main.py) are always correct
rem no matter where the user types "clovis" from.
pushd "%~dp0"

title Clovis

rem -- Auto-setup: run install.bat if .venv does not exist yet -----------------
if not exist ".venv\Scripts\python.exe" (
    echo.
    echo  Clovis is not set up yet. Running first-time setup...
    echo.
    call "install.bat"
    if errorlevel 1 (
        echo.
        echo  [ERROR] Setup failed. Fix the errors above and try again.
        popd
        pause
        exit /b 1
    )
)

rem -- Point to the venv Python directly (more reliable than activate.bat) -----
set "PYTHON=.venv\Scripts\python.exe"
set PYTHONIOENCODING=utf-8

rem -- Auto-start Ollama if installed but not already running ------------------
ollama --version >nul 2>&1
if not errorlevel 1 (
    ollama list >nul 2>&1
    if errorlevel 1 (
        echo  Starting Ollama in background...
        start "" /B ollama serve
        timeout /t 3 /nobreak >nul
    )
)

rem -- Mode selection menu -----------------------------------------------------
:menu
cls
echo.
echo  ==========================================
echo    Clovis  --  Your AI Desktop Assistant
echo  ==========================================
echo.
echo    How would you like to interact today?
echo.
echo    [1]  Chat Mode    - type commands (no mic needed)
echo    [2]  Voice Mode   - say "Clovis" to activate
echo    [3]  Voice Direct - speak without a wake word
echo    [4]  Hybrid Mode  - type OR speak each turn
echo    [5]  Exit
echo.
set "CHOICE="
set /p "CHOICE=   Enter your choice (1-5): "

if "!CHOICE!"=="1" goto chat
if "!CHOICE!"=="2" goto voice_wake
if "!CHOICE!"=="3" goto voice_direct
if "!CHOICE!"=="4" goto hybrid
if "!CHOICE!"=="5" goto bye

echo.
echo   Invalid choice. Please enter 1, 2, 3, 4 or 5.
timeout /t 2 /nobreak >nul
goto menu

rem -- Modes -------------------------------------------------------------------
:chat
echo.
echo   Starting Chat Mode...
echo.
"%PYTHON%" main.py --text
goto end

:voice_wake
echo.
echo   Starting Voice Mode (say "Clovis" to activate)...
echo.
"%PYTHON%" main.py
goto end

:voice_direct
echo.
echo   Starting Voice Mode (listening immediately)...
echo.
"%PYTHON%" main.py --no-wake-word
goto end

:hybrid
echo.
echo   Starting Hybrid Mode (type or press Enter to speak)...
echo.
"%PYTHON%" main.py --hybrid
goto end

:bye
echo.
echo   Goodbye!
popd
exit /b 0

:end
popd
echo.
echo   Clovis has exited. Press any key to close.
pause >nul
