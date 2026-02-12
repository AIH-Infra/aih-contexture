# DocLayout-YOLO Docker 部署指南

## 概述

DocLayout-YOLO 是基于 YOLOv10 的文档版面分析模型，专门用于检测文档中的各种元素（文本、标题、图片、表格等）。

**优势**：
- 速度快（GPU 上可达实时）
- 准确度高（专门针对文档训练）
- 资源占用少（比 VLM 小得多）
- 可完美替代 Surya Layout

## 系统要求

### 硬件要求
- **GPU**：NVIDIA GPU（推荐 6GB+ 显存）
- **内存**：8GB+ RAM
- **存储**：10GB+ 可用空间

### 软件要求
- **Docker**：20.10+
- **NVIDIA Docker Runtime**（用于 GPU 支持）
- **操作系统**：
  - Linux（推荐）
  - Windows + WSL2 + Docker Desktop
  - macOS（仅 CPU，不推荐）

## 在 Windows 上部署（使用 WSL2）

### 步骤 1: 安装 WSL2 和 Docker Desktop

1. **启用 WSL2**（如果尚未安装）：
```powershell
# 在 PowerShell（管理员）中运行
wsl --install
wsl --set-default-version 2
```

2. **安装 Docker Desktop**：
   - 下载：https://www.docker.com/products/docker-desktop
   - 安装时确保启用 "Use WSL 2 based engine"
   - 在设置中启用 "Resources > WSL Integration"

3. **安装 NVIDIA Container Toolkit**（在 WSL2 中）：
```bash
# 进入 WSL2
wsl

# 添加 NVIDIA 仓库
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

# 安装
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit

# 重启 Docker
sudo systemctl restart docker
```

### 步骤 2: 构建 DocLayout-YOLO Docker 镜像

创建项目目录：
```bash
mkdir -p ~/doclayout-yolo
cd ~/doclayout-yolo
```

创建 `Dockerfile`：
```dockerfile
FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

# 设置环境变量
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    git \
    libgl1-mesa-glx \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 安装 Python 依赖
RUN pip3 install --no-cache-dir \
    torch==2.1.0 \
    torchvision==0.16.0 \
    ultralytics==8.0.196 \
    fastapi==0.104.1 \
    uvicorn[standard]==0.24.0 \
    python-multipart==0.0.6 \
    pillow==10.1.0 \
    numpy==1.24.3 \
    opencv-python-headless==4.8.1.78

# 复制应用代码
COPY app.py /app/
COPY models/ /app/models/

# 暴露端口
EXPOSE 11900

# 启动命令
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "11900"]
```

创建 `app.py`（FastAPI 服务）：
```python
"""
DocLayout-YOLO Web Service
提供与 Marker 兼容的 HTTP API
"""
import io
import json
from typing import List, Dict, Any

import cv2
import numpy as np
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse
from PIL import Image
from ultralytics import YOLO

app = FastAPI(title="DocLayout-YOLO Service")

# 加载模型（启动时）
MODEL_PATH = "/app/models/doclayout_yolo_docstructbench_imgsz1024.pt"
model = None

# 标签映射（DocLayout-YOLO → Marker）
LABEL_MAPPING = {
    0: "Text",
    1: "Title",  # 映射到 SectionHeader
    2: "Figure",
    3: "Table",
    4: "Caption",
    5: "Equation",
    6: "List",  # 映射到 ListItem
    7: "Footer",  # 映射到 PageFooter
    8: "Header",  # 映射到 PageHeader
}

MARKER_LABEL_MAPPING = {
    "Title": "SectionHeader",
    "List": "ListItem",
    "Footer": "PageFooter",
    "Header": "PageHeader",
}


@app.on_event("startup")
async def load_model():
    """启动时加载模型"""
    global model
    try:
        model = YOLO(MODEL_PATH)
        print(f"✅ Model loaded: {MODEL_PATH}")
    except Exception as e:
        print(f"❌ Failed to load model: {e}")
        raise


@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "model_loaded": model is not None,
        "model_path": MODEL_PATH
    }


@app.post("/detect")
async def detect_layout(
    image: UploadFile = File(...),
    confidence_threshold: float = Form(0.25)
):
    """
    版面检测接口

    Args:
        image: 上传的图像文件
        confidence_threshold: 置信度阈值

    Returns:
        JSON 格式的检测结果
    """
    if model is None:
        return JSONResponse(
            status_code=503,
            content={"error": "Model not loaded"}
        )

    try:
        # 读取图像
        image_bytes = await image.read()
        image_array = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

        if img is None:
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid image"}
            )

        # 运行检测
        results = model(img, conf=confidence_threshold, verbose=False)

        # 解析结果
        detections = []
        for result in results:
            boxes = result.boxes
            for box in boxes:
                # 获取边界框坐标（xyxy 格式）
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()

                # 转换为 polygon 格式（Marker 需要）
                polygon = [
                    [float(x1), float(y1)],  # 左上
                    [float(x2), float(y1)],  # 右上
                    [float(x2), float(y2)],  # 右下
                    [float(x1), float(y2)],  # 左下
                ]

                # 获取类别和置信度
                cls = int(box.cls[0].cpu().numpy())
                conf = float(box.conf[0].cpu().numpy())

                # 映射标签
                label = LABEL_MAPPING.get(cls, "Text")
                marker_label = MARKER_LABEL_MAPPING.get(label, label)

                detections.append({
                    "label": marker_label,
                    "polygon": polygon,
                    "confidence": conf
                })

        return {
            "detections": detections,
            "image_size": {
                "width": img.shape[1],
                "height": img.shape[0]
            }
        }

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@app.post("/batch_detect")
async def batch_detect_layout(
    images: List[UploadFile] = File(...),
    confidence_threshold: float = Form(0.25)
):
    """批量版面检测"""
    results = []

    for img_file in images:
        result = await detect_layout(img_file, confidence_threshold)
        results.append(result)

    return {"results": results}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=11900)
```

### 步骤 3: 下载模型

```bash
# 创建模型目录
mkdir -p models

# 下载 DocLayout-YOLO 模型
# 方法 1: 从 Hugging Face 下载
wget https://huggingface.co/juliozhao/DocLayout-YOLO-DocStructBench/resolve/main/doclayout_yolo_docstructbench_imgsz1024.pt \
    -O models/doclayout_yolo_docstructbench_imgsz1024.pt

# 方法 2: 从 GitHub Release 下载
# wget https://github.com/opendatalab/DocLayout-YOLO/releases/download/v1.0/doclayout_yolo_docstructbench_imgsz1024.pt \
#     -O models/doclayout_yolo_docstructbench_imgsz1024.pt
```

### 步骤 4: 构建和运行 Docker 容器

```bash
# 构建镜像
docker build -t doclayout-yolo:latest .

# 运行容器（GPU 支持）
docker run -d \
    --name doclayout-yolo \
    --gpus all \
    -p 11900:11900 \
    -v $(pwd)/models:/app/models \
    doclayout-yolo:latest

# 查看日志
docker logs -f doclayout-yolo
```

### 步骤 5: 测试服务

```bash
# 健康检查
curl http://localhost:11900/health

# 测试检测（使用测试图像）
curl -X POST http://localhost:11900/detect \
    -F "image=@test.png" \
    -F "confidence_threshold=0.25"
```

## 在 Marker 中使用

### 配置 Streamlit UI

1. 选择 **版面识别后端** → `🎯 DocLayout-YOLO（Docker 服务）`
2. 设置 **YOLO 服务地址** → `http://localhost:11900`
3. 调整 **置信度阈值**（默认 0.25）

### 配置文件方式

```python
config = {
    "layout_backend": "yolo",
    "yolo_base_url": "http://localhost:11900",
    "yolo_model": "doclayout_yolo",
    "yolo_confidence_threshold": 0.25,
}
```

## 性能优化

### 1. 批处理
修改 `app.py` 支持批量处理以提高吞吐量。

### 2. 模型量化
使用 TensorRT 或 ONNX 加速推理：
```bash
# 导出为 ONNX
yolo export model=models/doclayout_yolo_docstructbench_imgsz1024.pt format=onnx
```

### 3. 多 Worker
```bash
docker run -d \
    --name doclayout-yolo \
    --gpus all \
    -p 11900:11900 \
    -e WORKERS=4 \
    doclayout-yolo:latest
```

## 故障排除

### GPU 不可用
```bash
# 检查 NVIDIA Docker 支持
docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi

# 如果失败，重新安装 nvidia-container-toolkit
```

### 模型加载失败
- 检查模型文件是否存在：`ls -lh models/`
- 检查文件权限：`chmod 644 models/*.pt`
- 查看容器日志：`docker logs doclayout-yolo`

### 端口冲突
```bash
# 更改端口映射
docker run -d --gpus all -p 12000:11900 doclayout-yolo:latest
```

## 与 Surya 的对比

| 特性 | Surya Layout | DocLayout-YOLO |
|------|--------------|----------------|
| **部署** | 内置，无需配置 | 需要 Docker 服务 |
| **速度** | 中等 | 快（GPU 上） |
| **准确度** | 中等 | 高 |
| **资源占用** | 中等 | 低 |
| **GPU 要求** | 可选 | 推荐 |
| **适用场景** | 通用文档 | 生产环境、批量处理 |

## 总结

**是否需要在 WSL 中构建？**
- **Windows 用户**：是的，推荐在 WSL2 中构建和运行
- **Linux 用户**：直接在主机上构建
- **macOS 用户**：可以构建，但只能用 CPU（不推荐）

**满足的条件**：
1. ✅ NVIDIA GPU（6GB+ 显存）
2. ✅ Docker + NVIDIA Container Toolkit
3. ✅ 下载 DocLayout-YOLO 模型
4. ✅ 实现兼容 Marker 的 HTTP API
5. ✅ 返回正确格式的检测结果

**优势**：
- 比 Surya 更快、更准确
- 比 VLM 更轻量、更稳定
- 适合生产环境和批量处理
