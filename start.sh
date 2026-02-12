#!/bin/bash

# AIH-Contexture 启动脚本 (Linux)

# 切换到脚本所在目录
cd "$(dirname "$0")"

echo ""
echo "══════════════════════════════════════════"
echo "  AIH-Contexture 启动中..."
echo "  面向人文学科的文献结构化提取平台"
echo "══════════════════════════════════════════"
echo ""

# 释放端口 6006（清理残留进程）
if command -v lsof &> /dev/null; then
    PID=$(lsof -ti:6006 2>/dev/null)
    if [ -n "$PID" ]; then
        echo "[信息] 正在释放端口 6006 (PID: $PID)..."
        kill -9 $PID 2>/dev/null
    fi
fi

# 检查虚拟环境
if [ ! -f ".venv/bin/activate" ]; then
    echo "[错误] 未找到虚拟环境，请先运行 ./install.sh"
    exit 1
fi

# 激活虚拟环境
source .venv/bin/activate

# 启动应用
echo "正在启动 Web 界面..."
echo ""
echo "访问地址: http://localhost:6006"
echo "按 Ctrl+C 停止服务"
echo ""

python contexture_app.py
