@echo off
REM Deepr installer / updater for Windows (cmd.exe wrapper)
REM Delegates to install.ps1 (single source of truth). Re-run to update.
REM   install.bat              install or update
REM   install.bat -Uninstall   remove

setlocal
set "SCRIPT_DIR=%~dp0"

powershell -ExecutionPolicy Bypass -NoProfile -File "%SCRIPT_DIR%install.ps1" %*
set "RC=%ERRORLEVEL%"

if not "%RC%"=="0" (
    echo.
    echo Installation failed with exit code %RC%.
)
exit /b %RC%
