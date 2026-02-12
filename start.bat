@echo off

:: AIH-Contexture 启动脚本 (Windows)

:: 切换到脚本所在目录
cd /d "%~dp0"

echo.
echo ==========================================
echo   AIH-Contexture 启动中...
echo   面向人文学科的文献结构化提取平台
echo ==========================================
echo.

:: 释放端口 6006（清理残留进程）
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :6006 ^| findstr LISTENING') do (
    taskkill /f /pid %%a >nul 2>&1
)

:: 检查虚拟环境
if not exist .venv\Scripts\activate.bat (
    echo [错误] 未找到虚拟环境
    echo 请先运行 install.bat 安装
    pause
    exit /b 1
)

:: 激活虚拟环境
call .venv\Scripts\activate.bat

:: 启动应用
echo 正在启动 Web 界面...
echo.
echo 访问地址: http://localhost:6006
echo 按 Ctrl+C 停止服务
echo.

python contexture_app.py

pause
