#!/bin/bash

# AIH-Contexture 启动脚本 (macOS)

# 切换到脚本所在目录
cd "$(dirname "$0")"

echo ""
echo "══════════════════════════════════════════"
echo "  AIH-Contexture 启动中..."
echo "  面向人文学科的文献结构化提取平台"
echo "══════════════════════════════════════════"
echo ""

# 检查虚拟环境
if [ ! -f ".venv/bin/activate" ]; then
    echo "[错误] 未找到虚拟环境，请先运行 ./install.command 或 ./install.sh"
    exit 1
fi

# 激活虚拟环境
source .venv/bin/activate

# 基础健康检查
if ! python -c "import streamlit, aih_contexture" >/dev/null 2>&1; then
    echo "[错误] 当前虚拟环境不完整，缺少 Streamlit 或项目依赖。"
    echo "请重新运行 ./install.command 或 ./install.sh 后再启动。"
    exit 1
fi

# 启动应用
echo "正在启动 Web 界面..."
echo ""
echo "默认从 8501 开始自动选择可用端口"
echo "将监听所有本地网口，并在启动后显示本机/局域网访问地址"
echo "按 Ctrl+C 停止服务"
echo ""

python contexture_app.py
