#!/bin/bash

# ============================================
#   AIH-Contexture 环境安装向导 (macOS/Linux)
#   面向人文学科的文献结构化提取平台
# ============================================

set -e

# 切换到脚本所在目录
cd "$(dirname "$0")"

# 镜像源配置
MIRROR_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
USE_MIRROR=0

# pip安装函数：失败自动切换镜像
pip_install() {
    if [ $USE_MIRROR -eq 1 ]; then
        pip install "$@" -i "$MIRROR_URL"
    else
        if ! pip install "$@" 2>/dev/null; then
            echo "[提示] 官方源连接失败，切换到清华镜像..."
            USE_MIRROR=1
            pip install "$@" -i "$MIRROR_URL"
        fi
    fi
}

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║         AIH-Contexture 环境安装向导                     ║"
echo "║       面向人文学科的文献结构化提取平台                  ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║                                                        ║"
echo "║  安装说明:                                             ║"
echo "║  - GPU 版 (NVIDIA): 需下载约 3~4 GB，约 15~30 分钟    ║"
echo "║  - CPU / Mac 版:    需下载约 1~1.5 GB，约 10~20 分钟  ║"
echo "║  - 实际耗时取决于网络速度，请保持网络畅通              ║"
echo "║  - 安装过程中请勿关闭终端窗口，耐心等待即可            ║"
echo "║                                                        ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ============================================
# 步骤 1: 检测 Python
# ============================================
echo "[1/5] 检测 Python 环境..."

PYTHON_CMD=""

# 按优先级检测 Python 版本 (3.12 > 3.11 > 3.10)
echo "[Info] 扫描已安装的 Python 版本..."

for ver in python3.12 python3.11 python3.10; do
    if command -v $ver &> /dev/null; then
        PYVER=$($ver --version 2>&1 | cut -d' ' -f2)
        echo "[Found] Python $PYVER"
        if [ -z "$PYTHON_CMD" ]; then
            PYTHON_CMD=$ver
        fi
    fi
done

# 如果没找到特定版本，检查 python3 或 python
if [ -z "$PYTHON_CMD" ]; then
    for cmd in python3 python; do
        if command -v $cmd &> /dev/null; then
            PYVER=$($cmd --version 2>&1 | cut -d' ' -f2)
            PYMAJOR=$(echo $PYVER | cut -d'.' -f1)
            PYMINOR=$(echo $PYVER | cut -d'.' -f2)
            if [ "$PYMAJOR" -eq 3 ] && [ "$PYMINOR" -ge 10 ] && [ "$PYMINOR" -le 12 ]; then
                PYTHON_CMD=$cmd
                echo "[Found] Python $PYVER"
                break
            fi
        fi
    done
fi

# 未找到兼容版本
if [ -z "$PYTHON_CMD" ]; then
    echo ""
    echo "[错误] 未找到兼容的 Python 版本"
    echo ""
    echo "需要: Python 3.10, 3.11, 或 3.12"
    echo ""
    echo "macOS 安装方式:"
    echo "  brew install python@3.12"
    echo ""
    echo "或从官网下载: https://www.python.org/downloads/release/python-3129/"
    echo ""
    exit 1
fi

# 显示选择的版本
PYVER=$($PYTHON_CMD --version 2>&1 | cut -d' ' -f2)
echo ""
echo "[OK] 使用 Python $PYVER"
echo ""

# ============================================
# 步骤 2: 创建虚拟环境
# ============================================
echo "[2/5] 创建虚拟环境..."

if [ -d ".venv" ]; then
    echo "[提示] 检测到已有虚拟环境 .venv"
    read -p "是否重新创建? (y/N): " RECREATE
    if [ "$RECREATE" = "y" ] || [ "$RECREATE" = "Y" ]; then
        rm -rf .venv
        $PYTHON_CMD -m venv .venv
    fi
else
    $PYTHON_CMD -m venv .venv
fi

if [ ! -f ".venv/bin/activate" ]; then
    echo "[错误] 虚拟环境创建失败"
    exit 1
fi

echo "[OK] 虚拟环境已就绪"
echo ""

# 激活虚拟环境
source .venv/bin/activate

# 升级 pip
echo "升级 pip..."
pip_install --upgrade pip -q

# ============================================
# 步骤 3: 硬件检测
# ============================================
echo "[3/5] 检测硬件环境..."
echo ""

IS_MAC=0
IS_APPLE_SILICON=0

# 检测操作系统
if [[ "$OSTYPE" == "darwin"* ]]; then
    IS_MAC=1
    # 检测 Apple Silicon
    if [[ $(uname -m) == "arm64" ]]; then
        IS_APPLE_SILICON=1
        echo "[检测到] Apple Silicon (M系列芯片)"
        echo "[提示] 将使用 MPS 加速"
    else
        echo "[检测到] Intel Mac"
    fi
else
    echo "[检测到] Linux 系统"
fi
echo ""

# ============================================
# 步骤 4: 安装 PyTorch
# ============================================
echo "[4/5] 安装 PyTorch..."
echo ""

if [ $IS_MAC -eq 1 ]; then
    echo "安装 PyTorch (macOS)..."
    pip_install torch torchvision
else
    # Linux - 检测 NVIDIA GPU
    if command -v nvidia-smi &> /dev/null; then
        echo "[检测到] NVIDIA GPU"
        nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || true
        echo ""
        echo "安装 PyTorch (CUDA 12.6)..."
        pip_install torch torchvision --index-url https://download.pytorch.org/whl/cu126
    else
        echo "安装 PyTorch (CPU)..."
        pip_install torch torchvision --index-url https://download.pytorch.org/whl/cpu
    fi
fi

echo "[OK] PyTorch 安装完成"
echo ""

# ============================================
# 步骤 5: 安装其他依赖
# ============================================
echo "[5/5] 安装项目依赖..."
echo ""

pip_install -r requirements.txt

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║                    安装完成！                           ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║  启动方式: ./start.sh                                  ║"
echo "║  访问地址: http://localhost:6006                       ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
