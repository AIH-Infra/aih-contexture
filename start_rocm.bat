@echo off
chcp 65001 >nul
:: Compatibility launcher for the ROCm build.
:: start.bat in this release is already bound to the dedicated ROCm conda environment.
call "%~dp0start.bat" %*
