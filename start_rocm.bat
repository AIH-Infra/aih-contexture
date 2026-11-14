@echo off
chcp 65001 >nul
:: Compatibility launcher for this checkout's local .venv.
:: Windows setup does not install ROCm; use only with a preconfigured environment.
call "%~dp0start.bat" %*
