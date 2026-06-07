@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "TARGET_DIR=%~1"

if "%TARGET_DIR%"=="" (
  powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%upgrade_from_0.1.ps1"
) else (
  powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%upgrade_from_0.1.ps1" -TargetDir "%TARGET_DIR%"
)

if errorlevel 1 (
  echo.
  echo Upgrade failed. Please read the error above.
  pause
  exit /b 1
)

echo.
echo Upgrade completed.
pause
