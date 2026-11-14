@echo off
chcp 65001 >nul
:: Compatibility launcher for this checkout's local .venv.
:: Windows setup installs CUDA or CPU PyTorch; it does not install ROCm.
call "%~dp0start.bat" %*
