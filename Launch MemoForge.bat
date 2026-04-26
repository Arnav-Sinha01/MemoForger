@echo off
setlocal

cd /d "%~dp0"

echo [MemoForge] Starting app...
echo.

python main.py
if %ERRORLEVEL% EQU 0 goto :eof

py -3.11 main.py
if %ERRORLEVEL% EQU 0 goto :eof

echo [MemoForge] Failed to start.
echo [MemoForge] Please ensure Python 3.11 is installed and available as 'python' or 'py'.
pause
