#!/bin/bash

# ============================================
#   AIH-Contexture 环境安装向导 (macOS/Linux)
#   面向人文学科的文献结构化提取平台
# ============================================

set -e

# 切换到脚本所在目录
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)"
cd "$SCRIPT_DIR"

# 镜像源配置
MIRROR_URL="https://pypi.tuna.tsinghua.edu.cn/simple"
USE_MIRROR=0

# pip安装函数：失败自动切换镜像
pip_install() {
    if [ $USE_MIRROR -eq 1 ]; then
        "$VENV_PYTHON" -m pip install "$@" -i "$MIRROR_URL"
    else
        if ! "$VENV_PYTHON" -m pip install "$@" 2>/dev/null; then
            echo "[提示] 官方源连接失败，切换到清华镜像..."
            USE_MIRROR=1
            "$VENV_PYTHON" -m pip install "$@" -i "$MIRROR_URL"
        fi
    fi
}

install_torch_profile() {
    if [ -n "$TORCH_INDEX" ]; then
        "$VENV_PYTHON" -m pip install --isolated --no-cache-dir --upgrade --force-reinstall \
            --index-url "$TORCH_INDEX" "torch==2.13.0" "torchvision==0.28.0"
    else
        "$VENV_PYTHON" -m pip install --isolated --no-cache-dir --upgrade --force-reinstall \
            "torch==2.13.0" "torchvision==0.28.0"
    fi
}

verify_torch_profile() {
    case "$TORCH_PROFILE" in
        cuda)
            "$VENV_PYTHON" -c "import sys, torch, torchvision; expected='$TORCH_CUDA_EXPECTED'; torch_ok=torch.__version__.split('+', 1)[0] == '2.13.0'; vision_ok=torchvision.__version__.split('+', 1)[0] == '0.28.0'; actual=torch.version.cuda; available=torch.cuda.is_available(); print(f'torch={torch.__version__}; torchvision={torchvision.__version__}; cuda_build={actual}; cuda_available={available}'); sys.exit(0 if torch_ok and vision_ok and actual == expected and available else 1)"
            ;;
        mps)
            "$VENV_PYTHON" -c "import sys, torch, torchvision; torch_ok=torch.__version__.split('+', 1)[0] == '2.13.0'; vision_ok=torchvision.__version__.split('+', 1)[0] == '0.28.0'; built=torch.backends.mps.is_built(); available=torch.backends.mps.is_available(); print(f'torch={torch.__version__}; torchvision={torchvision.__version__}; mps_built={built}; mps_available={available}'); sys.exit(0 if torch_ok and vision_ok and built and available else 1)"
            ;;
        cpu)
            "$VENV_PYTHON" -c "import sys, torch, torchvision; torch_ok=torch.__version__.split('+', 1)[0] == '2.13.0'; vision_ok=torchvision.__version__.split('+', 1)[0] == '0.28.0'; actual=torch.version.cuda; available=torch.cuda.is_available(); print(f'torch={torch.__version__}; torchvision={torchvision.__version__}; cuda_build={actual}; cuda_available={available}'); sys.exit(0 if torch_ok and vision_ok and actual is None and not available else 1)"
            ;;
        *)
            echo "[错误] 未知 PyTorch profile: $TORCH_PROFILE" >&2
            return 1
            ;;
    esac
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
    if [ ! -x ".venv/bin/python" ] || [ ! -f ".venv/bin/activate" ]; then
        echo "[警告] 当前 .venv 不完整或已损坏。"
        read -r -p "是否移除本目录中的 .venv 并重新创建? (y/N): " RECREATE
    else
        read -r -p "是否移除本目录中的 .venv 并重新创建? (y/N): " RECREATE
    fi
    if [ "$RECREATE" = "y" ] || [ "$RECREATE" = "Y" ]; then
        rm -rf .venv
        if [ -d ".venv" ]; then
            echo "[错误] 无法移除旧的 .venv。请关闭占用它的终端或编辑器后重试。"
            exit 1
        fi
        $PYTHON_CMD -m venv .venv
    elif [ ! -x ".venv/bin/python" ] || [ ! -f ".venv/bin/activate" ]; then
        echo "[错误] 当前 .venv 不完整或已损坏。"
        echo "请重新运行安装脚本并选择 y 重建，或检查后手动移除 .venv。"
        exit 1
    fi
else
    $PYTHON_CMD -m venv .venv
fi

if [ ! -x ".venv/bin/python" ] || [ ! -f ".venv/bin/activate" ]; then
    echo "[错误] 虚拟环境创建失败"
    exit 1
fi

echo "[OK] 虚拟环境已就绪"
echo ""

# 激活虚拟环境
source .venv/bin/activate
VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python"

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

TORCH_PROFILE=""
TORCH_CUDA_EXPECTED=""
TORCH_INDEX=""

if [ $IS_MAC -eq 1 ]; then
    if [ $IS_APPLE_SILICON -eq 1 ]; then
        TORCH_PROFILE="mps"
        echo "安装 PyTorch (Apple Silicon MPS)..."
    else
        TORCH_PROFILE="cpu"
        echo "安装 PyTorch (Intel Mac CPU)..."
    fi
else
    # Linux - 检测 NVIDIA GPU
    if command -v nvidia-smi &> /dev/null; then
        echo "[检测到] NVIDIA GPU"
        nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null || true
        echo ""
        while true; do
            echo "请选择经过验证的 PyTorch profile："
            echo "  [1] CUDA 12.6（推荐，NVIDIA 兼容范围最广）"
            echo "  [2] CUDA 13.0（需要兼容 CUDA 13.0 的 NVIDIA 驱动）"
            echo "  [3] CUDA 13.2（需要兼容 CUDA 13.2 的 NVIDIA 驱动）"
            echo "  [4] 仅 CPU"
            CUDA_CHOICE=""
            read -r -p "选择 [1-4，默认 1]: " CUDA_CHOICE || CUDA_CHOICE=""
            [ -z "$CUDA_CHOICE" ] && CUDA_CHOICE="1"
            case "$CUDA_CHOICE" in
                1)
                    TORCH_PROFILE="cuda"
                    TORCH_CUDA_EXPECTED="12.6"
                    TORCH_INDEX="https://download.pytorch.org/whl/cu126"
                    break
                    ;;
                2)
                    TORCH_PROFILE="cuda"
                    TORCH_CUDA_EXPECTED="13.0"
                    TORCH_INDEX="https://download.pytorch.org/whl/cu130"
                    break
                    ;;
                3)
                    TORCH_PROFILE="cuda"
                    TORCH_CUDA_EXPECTED="13.2"
                    TORCH_INDEX="https://download.pytorch.org/whl/cu132"
                    break
                    ;;
                4)
                    TORCH_PROFILE="cpu"
                    TORCH_INDEX="https://download.pytorch.org/whl/cpu"
                    break
                    ;;
                *)
                    echo "[错误] 无效选择 \"$CUDA_CHOICE\"。请输入 1、2、3 或 4。"
                    echo ""
                    ;;
            esac
        done
    else
        TORCH_PROFILE="cpu"
        TORCH_INDEX="https://download.pytorch.org/whl/cpu"
        echo "安装 PyTorch (CPU)..."
    fi
fi

if ! install_torch_profile; then
    echo "[错误] PyTorch 安装失败。未执行 CPU 静默回退。" >&2
    exit 1
fi
if ! verify_torch_profile; then
    echo "[错误] 安装的 PyTorch 与预期 profile 不匹配。" >&2
    echo "请检查网络、NVIDIA 驱动或 Apple MPS 可用性。" >&2
    exit 1
fi

echo "[OK] PyTorch profile 验证通过: $TORCH_PROFILE"
echo ""

# ============================================
# 步骤 5: 安装其他依赖
# ============================================
echo "[5/5] 安装项目依赖..."
echo ""

pip_install -r requirements.txt

if ! verify_torch_profile; then
    echo "[错误] 项目依赖安装后 PyTorch profile 发生变化。" >&2
    exit 1
fi

echo ""
echo "注册本地 Contexture 命令入口..."
pip_install -e . --no-deps

if ! "$VENV_PYTHON" -c "import streamlit, aih_contexture; from aih_contexture.scripts.doctor import doctor_cli" >/dev/null 2>&1; then
    echo "[错误] 安装验证失败，请检查上方依赖安装日志。"
    exit 1
fi

echo ""
echo "[可选] 检测 Tesseract OCR..."
if command -v tesseract >/dev/null 2>&1; then
    echo "[Found] $(command -v tesseract)"
    tesseract --version | head -n 1 || true
else
    echo "[提示] 未发现 Tesseract。Tesseract OCR 后端是可选项，主安装不受影响。"
    if [ $IS_MAC -eq 1 ]; then
        if command -v brew >/dev/null 2>&1; then
            read -r -p "是否尝试通过 Homebrew 安装 Tesseract? (y/N): " INSTALL_TESS
            if [ "$INSTALL_TESS" = "y" ] || [ "$INSTALL_TESS" = "Y" ]; then
                brew install tesseract || true
            fi
        else
            echo "macOS 可安装 Homebrew 后运行: brew install tesseract"
        fi
    else
        echo "Linux 常见安装命令:"
        echo "  Ubuntu/Debian: sudo apt install tesseract-ocr"
        echo "  Fedora:        sudo dnf install tesseract"
        echo "  Arch:          sudo pacman -S tesseract"
    fi
    echo "也可以设置 CONTEXTURE_TESSERACT_CMD 指向 tesseract 可执行文件。"
fi

echo ""
echo "╔════════════════════════════════════════════════════════════════════╗"
echo "║                           安装完成！                              ║"
echo "╠════════════════════════════════════════════════════════════════════╣"
echo "║  启动方式: ./start.sh                                             ║"
echo "║  后端检查: ./.venv/bin/contexture_doctor                          ║"
echo "║  启动后将从 8501 开始自动选择可用端口，并显示实际访问地址        ║"
echo "║  默认安装保证主流程可用；扩展文档格式可能仍需额外依赖            ║"
echo "║  首次使用 Pipeline / Surya 时会联网下载模型，首次可能较慢        ║"
echo "╚════════════════════════════════════════════════════════════════════╝"
echo ""
