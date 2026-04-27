@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: ============================================
::   AIH-Contexture Environment Setup (Windows)
:: ============================================

echo.
echo ============================================================
echo    AIH-Contexture 环境安装向导
echo    面向人文学科的文献结构化提取平台
echo ============================================================
echo.
echo    安装说明:
echo    - GPU 版 (NVIDIA): 需下载约 3~4 GB，预计 15~30 分钟
echo    - CPU 版:          需下载约 1~1.5 GB，预计 10~20 分钟
echo    - 实际耗时取决于网络速度，请保持网络畅通
echo    - 安装过程中请勿关闭此窗口，耐心等待即可
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

if exist .venv (
    echo [Info] Found existing .venv
    set /p RECREATE="Recreate? (y/N): "
    if /i "!RECREATE!"=="y" (
        echo Removing old environment...
        rmdir /s /q .venv
        !PYTHON_CMD! -m venv .venv
    )
) else (
    !PYTHON_CMD! -m venv .venv
)

if not exist .venv\Scripts\activate.bat (
    echo [Error] Failed to create virtual environment
    pause
    exit /b 1
)

echo [OK] Virtual environment ready
echo.

:: Activate
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip -q

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
        pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
    ) else if "!CUDA_CHOICE!"=="2" (
        echo Installing PyTorch with CUDA 12.8...
        pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
    ) else if "!CUDA_CHOICE!"=="3" (
        echo Installing PyTorch with CUDA 13.0...
        pip install torch torchvision --index-url https://download.pytorch.org/whl/cu130
    ) else (
        echo Installing PyTorch CPU version...
        pip install torch torchvision
    )
) else (
    echo Installing PyTorch CPU version...
    pip install torch torchvision
)

if %errorlevel% neq 0 (
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

pip install -r requirements.txt

if %errorlevel% neq 0 (
    echo.
    echo [Error] Dependencies installation failed
    pause
    exit /b 1
)

echo.
echo ============================================================
echo    安装完成！
echo ============================================================
echo.
echo    启动方式: 双击 start.bat 或在命令行运行 start.bat
echo    启动后将从 8501 开始自动选择可用端口，并显示实际访问地址
echo    默认安装保证主流程可用；扩展文档格式可能仍需额外依赖
echo    首次使用 Pipeline / Surya 时会联网下载模型，首次可能较慢
echo.
echo ============================================================
echo.

pause
