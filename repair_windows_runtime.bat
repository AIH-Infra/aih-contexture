@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo.
echo AIH-Contexture Windows runtime repair
echo This reruns install.bat to reinstall and verify the selected PyTorch profile.
echo Windows will not restart automatically.
echo.

call "%~dp0install.bat" %*
set "REPAIR_EXIT=%errorlevel%"

echo.
if "%REPAIR_EXIT%"=="0" (
    echo [OK] Runtime repair completed.
) else (
    echo [Error] Runtime repair failed with exit code %REPAIR_EXIT%.
)
echo.
pause
exit /b %REPAIR_EXIT%
