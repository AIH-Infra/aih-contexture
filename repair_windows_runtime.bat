@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo Re-running the standard Contexture installer to restore project dependencies.
call "%~dp0install.bat"
set "REPAIR_EXIT=%errorlevel%"
if not "%REPAIR_EXIT%"=="0" (
    echo [Error] Reinstallation failed with exit code %REPAIR_EXIT%.
)
exit /b %REPAIR_EXIT%
