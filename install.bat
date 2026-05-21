@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

:: Avoid inherited pip settings that can force stale local caches or hash checks.
set "PIP_NO_INDEX="
set "PIP_REQUIRE_HASHES="
set "PIP_FIND_LINKS="
set "PIP_CACHE_DIR="

:: ============================================
::   AIH-Contexture Environment Setup (Windows)
:: ============================================

echo.
echo ============================================================
echo    AIH-Contexture Environment Setup
echo    Literature structure extraction platform
echo ============================================================
echo.
echo    Notes:
echo    - GPU build (NVIDIA): downloads about 3-4 GB, usually 15-30 minutes
echo    - CPU build:          downloads about 1-1.5 GB, usually 10-20 minutes
echo    - Actual time depends on your network speed
echo    - Keep this window open until setup finishes
echo.
echo ============================================================
echo.

:: ============================================
:: Step 1: Check Python
:: ============================================
echo [1/5] Checking Python...

set PYTHON_CMD=
set BEST_MINOR=0

:: Try py launcher first (Windows Python Launcher)
where py >nul 2>&1
if %errorlevel%==0 (
    echo [Info] Scanning installed Python versions...

    :: Check for Python 3.12
    py -3.12 --version >nul 2>&1
    if !errorlevel!==0 (
        set PYTHON_CMD=py -3.12
        set BEST_MINOR=12
        for /f "tokens=2" %%v in ('py -3.12 --version 2^>^&1') do echo [Found] Python %%v
    )

    :: Check for Python 3.11 if no 3.12
    if "!PYTHON_CMD!"=="" (
        py -3.11 --version >nul 2>&1
        if !errorlevel!==0 (
            set PYTHON_CMD=py -3.11
            set BEST_MINOR=11
            for /f "tokens=2" %%v in ('py -3.11 --version 2^>^&1') do echo [Found] Python %%v
        )
    )

    :: Check for Python 3.10 if no 3.11
    if "!PYTHON_CMD!"=="" (
        py -3.10 --version >nul 2>&1
        if !errorlevel!==0 (
            set PYTHON_CMD=py -3.10
            set BEST_MINOR=10
            for /f "tokens=2" %%v in ('py -3.10 --version 2^>^&1') do echo [Found] Python %%v
        )
    )
)

:: Fallback to python command if py launcher didn't find compatible version
if "!PYTHON_CMD!"=="" (
    where python >nul 2>&1
    if !errorlevel!==0 (
        for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
        for /f "tokens=1,2 delims=." %%a in ("!PYVER!") do (
            set PYMAJOR=%%a
            set PYMINOR=%%b
        )
        if !PYMAJOR!==3 if !PYMINOR! geq 10 if !PYMINOR! leq 12 (
            set PYTHON_CMD=python
            set BEST_MINOR=!PYMINOR!
            echo [Found] Python !PYVER!
        )
    )
)

:: No compatible Python found
if "!PYTHON_CMD!"=="" (
    echo.
    echo [Error] No compatible Python found
    echo.
    echo Required: Python 3.10, 3.11, or 3.12
    echo.
    echo Please install Python 3.12 from:
    echo https://www.python.org/downloads/release/python-3129/
    echo.
    echo Make sure to check "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

:: Get selected Python version
for /f "tokens=2" %%i in ('!PYTHON_CMD! --version 2^>^&1') do set PYVER=%%i
echo.
echo [OK] Using Python %PYVER%
echo.

:: ============================================
:: Step 2: Create Virtual Environment
:: ============================================
echo [2/5] Creating virtual environment...

set VENV_OK=0
if exist ".venv\Scripts\python.exe" if exist ".venv\Scripts\activate.bat" set VENV_OK=1

if exist ".venv\" (
    echo [Info] Found existing .venv
    set RECREATE=
    if "!VENV_OK!"=="0" (
        echo [Warning] Existing .venv is incomplete or broken.
        set /p RECREATE="Remove this .venv and recreate it? (y/N): "
    ) else (
        set /p RECREATE="Recreate? (y/N): "
    )
    if /i "!RECREATE!"=="y" (
        echo Removing old environment...
        rmdir /s /q .venv
        if exist ".venv\" (
            echo [Error] Failed to remove old .venv
            echo Please close any terminal or editor using .venv, then run install.bat again.
            pause
            exit /b 1
        )
        !PYTHON_CMD! -m venv .venv
        if !errorlevel! neq 0 (
            echo.
            echo [Error] Failed to create virtual environment
            echo Python venv/ensurepip failed. Try repairing or reinstalling Python, then run install.bat again.
            echo Selected Python: !PYTHON_CMD!
            pause
            exit /b 1
        )
    ) else if "!VENV_OK!"=="0" (
        echo.
        echo [Error] Existing .venv is incomplete or broken
        echo Please rerun install.bat and choose y to recreate it, or remove .venv manually after checking it.
        pause
        exit /b 1
    )
) else (
    !PYTHON_CMD! -m venv .venv
    if !errorlevel! neq 0 (
        echo.
        echo [Error] Failed to create virtual environment
        echo Python venv/ensurepip failed. Try repairing or reinstalling Python, then run install.bat again.
        echo Selected Python: !PYTHON_CMD!
        pause
        exit /b 1
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo [Error] Failed to create virtual environment Python
    pause
    exit /b 1
)

if not exist ".venv\Scripts\activate.bat" (
    echo [Error] Failed to create virtual environment
    pause
    exit /b 1
)

echo [OK] Virtual environment ready
echo.

:: Activate
call .venv\Scripts\activate.bat
".venv\Scripts\python.exe" -m pip install --upgrade pip -q --no-cache-dir
if !errorlevel! neq 0 (
    echo.
    echo [Error] Failed to upgrade pip
    echo Please check your Python installation and network connection
    pause
    exit /b 1
)

:: ============================================
:: Step 3: Hardware Detection
:: ============================================
echo [3/5] Detecting hardware...
echo.

set HAS_NVIDIA=0

where nvidia-smi >nul 2>&1
if %errorlevel%==0 (
    for /f "tokens=*" %%i in ('nvidia-smi --query-gpu=name --format=csv,noheader 2^>nul') do (
        echo [Found] NVIDIA GPU: %%i
        set HAS_NVIDIA=1
    )
    for /f "tokens=9" %%i in ('nvidia-smi 2^>nul ^| findstr "CUDA Version"') do (
        echo [Found] CUDA Version: %%i
    )
) else (
    echo [Info] No NVIDIA GPU detected, will use CPU mode
)
echo.

:: ============================================
:: Step 4: Install PyTorch
:: ============================================
echo [4/5] Installing PyTorch...
echo.

if %HAS_NVIDIA%==1 (
    echo NVIDIA GPU detected. Select CUDA version:
    echo.
    echo   [1] CUDA 12.6 (Recommended)
    echo   [2] CUDA 12.8
    echo   [3] CUDA 13.0 (Latest)
    echo   [4] CPU only
    echo.
    set /p CUDA_CHOICE="Select [1-4, default=1]: "
    if "!CUDA_CHOICE!"=="" set CUDA_CHOICE=1

    if "!CUDA_CHOICE!"=="1" (
        echo Installing PyTorch with CUDA 12.6...
        ".venv\Scripts\python.exe" -m pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu126
    ) else if "!CUDA_CHOICE!"=="2" (
        echo Installing PyTorch with CUDA 12.8...
        ".venv\Scripts\python.exe" -m pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu128
    ) else if "!CUDA_CHOICE!"=="3" (
        echo Installing PyTorch with CUDA 13.0...
        ".venv\Scripts\python.exe" -m pip install --no-cache-dir torch torchvision --index-url https://download.pytorch.org/whl/cu130
    ) else (
        echo Installing PyTorch CPU version...
        ".venv\Scripts\python.exe" -m pip install --no-cache-dir torch torchvision
    )
) else (
    echo Installing PyTorch CPU version...
    ".venv\Scripts\python.exe" -m pip install --no-cache-dir torch torchvision
)

if !errorlevel! neq 0 (
    echo.
    echo [Error] PyTorch installation failed
    echo Please check your network connection
    pause
    exit /b 1
)

echo [OK] PyTorch installed
echo.

:: ============================================
:: Step 5: Install Dependencies
:: ============================================
echo [5/5] Installing dependencies...
echo.

".venv\Scripts\python.exe" -m pip install --no-cache-dir -r requirements.txt

if !errorlevel! neq 0 (
    echo.
    echo [Error] Dependencies installation failed
    pause
    exit /b 1
)

echo.
echo ============================================================
echo    Setup complete!
echo ============================================================
echo.
echo    Start: double-click start.bat, or run start.bat in a terminal
echo    The app will choose an available port starting from 8501
echo    The default install covers the main PDF/image workflow
echo    First Pipeline / Surya use may download models and take longer
echo.
echo ============================================================
echo.

pause
