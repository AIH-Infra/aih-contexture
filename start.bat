@echo off
chcp 65001 >nul
setlocal

:: AIH-Contexture start script (Windows)

:: Switch to the script directory
cd /d "%~dp0"

echo.
echo ==========================================
echo   Starting AIH-Contexture...
echo   Literature structure extraction platform
echo ==========================================
echo.

:: Check virtual environment
if not exist ".venv\Scripts\python.exe" (
    echo [Error] Virtual environment Python not found
    echo Please run install.bat first
    pause
    exit /b 1
)

:: Activate virtual environment
call .venv\Scripts\activate.bat

:: Basic health check
".venv\Scripts\python.exe" -c "import streamlit, aih_contexture" >nul 2>nul
if %errorlevel% neq 0 (
    echo [Error] The virtual environment is incomplete
    echo Missing Streamlit or project dependencies. Please run install.bat again.
    pause
    exit /b 1
)

:: Probe PyTorch in an isolated child process so DLL failures do not crash the UI.
".venv\Scripts\python.exe" -c "import torch; print(torch.__version__, torch.cuda.is_available())" > ".torch_startup_check.log" 2>&1
if %errorlevel% neq 0 (
    echo [Warning] PyTorch could not be loaded. Local Surya/PyTorch backends will be unavailable.
    echo [Warning] API backends and JSON rerendering can still be used.
    echo [Action] Run repair_windows_runtime.bat, restart Windows, then start Contexture again.
    echo [Detail] See .torch_startup_check.log for the original import error.
    echo.
)

:: Set model cache directories
set "HF_HOME=%~dp0.cache\huggingface"
set "TRANSFORMERS_CACHE=%~dp0.cache\huggingface"
set "TORCH_HOME=%~dp0.cache\torch"

:: Start application
echo [Code] "%CD%"
echo [Python] "%CD%\.venv\Scripts\python.exe"
echo Starting the web UI...
echo.
echo The app will choose an available port starting from 8501
echo It will listen on local network interfaces and print access URLs
echo Press Ctrl+C to stop
echo.

".venv\Scripts\python.exe" contexture_app.py

pause
