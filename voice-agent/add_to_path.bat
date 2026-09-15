@echo off
setlocal EnableDelayedExpansion
title Clovis -- Add to PATH

rem -- Resolve the voice-agent directory ----------------------------------------
set "CLOVIS_DIR=%~dp0"
if "!CLOVIS_DIR:~-1!"=="\" set "CLOVIS_DIR=!CLOVIS_DIR:~0,-1!"

echo.
echo  ==========================================
echo    Clovis -- Add to System PATH
echo  ==========================================
echo.
echo  This will add the following directory to your
echo  user PATH so you can type "clovis" from any terminal:
echo.
echo    !CLOVIS_DIR!
echo.

rem -- Add to user PATH via PowerShell ------------------------------------------
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$dir = '%CLOVIS_DIR%'; $cur = [Environment]::GetEnvironmentVariable('PATH','User'); if ($cur -notlike ('*' + $dir + '*')) { [Environment]::SetEnvironmentVariable('PATH', $cur + ';' + $dir, 'User'); Write-Host '[OK] Added to PATH.' } else { Write-Host '[OK] Already in PATH.' }"

if errorlevel 1 (
    echo.
    echo  [ERROR] Failed to update PATH.
    pause
    exit /b 1
)

echo.
echo  ==========================================
echo   You can now type  clovis  in any terminal.
echo   (Open a NEW terminal window first.)
echo  ==========================================
echo.
pause
exit /b 0
