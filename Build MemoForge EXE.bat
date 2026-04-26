@echo off
setlocal

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Build-MemoForgeExe.ps1"
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [MemoForge Build] Build failed.
    pause
)
