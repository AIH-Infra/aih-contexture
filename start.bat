@echo off
chcp 65001 >nul

:: AIH-Contexture 启动脚本 (Windows)

:: 切换到脚本所在目录
cd /d "%~dp0"

echo.
echo ==========================================
echo   AIH-Contexture 启动中...
echo   面向人文学科的文献结构化提取平台
echo ==========================================
echo.

:: 检查虚拟环境
if not exist .venv\Scripts\python.exe (
    echo [错误] 未找到虚拟环境 Python
    echo 请先运行 install.bat 安装
    pause
    exit /b 1
)

:: 激活虚拟环境
call .venv\Scripts\activate.bat

:: 基础健康检查
.venv\Scripts\python.exe -c "import streamlit, aih_contexture" >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] 当前虚拟环境不完整，缺少 Streamlit 或项目依赖。
    echo 请重新运行 install.bat 后再启动。
    pause
    exit /b 1
)

:: 设置模型缓存目录
set HF_HOME=%~dp0.cache\huggingface
set TRANSFORMERS_CACHE=%~dp0.cache\huggingface
set TORCH_HOME=%~dp0.cache\torch

:: 启动应用
echo 正在启动 Web 界面...
echo.
echo 默认从 8501 开始自动选择可用端口
echo 将监听所有本地网口，并在启动后显示本机/局域网访问地址
echo 按 Ctrl+C 停止服务
echo.

.venv\Scripts\python.exe contexture_app.py

pause
