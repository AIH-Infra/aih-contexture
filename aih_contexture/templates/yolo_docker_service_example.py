"""
DocLayout-YOLO Docker 服务示例（FastAPI）

这是一个最小的 FastAPI 服务示例，展示如何包装 DocLayout-YOLO 模型
供 Marker 的 DocLayoutYoloService 调用。

部署说明：
1. 构建 Docker 镜像（包含 YOLO 模型和依赖）
2. 运行容器并暴露端口（默认 11900）
3. Marker 通过 HTTP API 调用此服务进行版面识别

API 约定：
- GET /health: 健康检查
- POST /detect: 版面检测（Marker 期望的标准端点）
- POST /predict: 版面检测（备选端点名）

依赖项（需要在 Docker 镜像中安装）：
pip install fastapi uvicorn pillow numpy torch torchvision ultralytics
pip install doclayout-yolo  # 如果有 PyPI 包的话
"""

from typing import List, Dict, Any, Optional
from io import BytesIO
import logging

from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from PIL import Image
import uvicorn

# 假设你已经安装了 DocLayout-YOLO 或有等价的 YOLO 推理模块
# 这里使用伪代码示例，实际需要替换为真实的 YOLO 加载和推理逻辑
try:
    # 示例 1: 使用 ultralytics YOLO
    from ultralytics import YOLO
    # 或者
    # 示例 2: 使用自定义的 DocLayout-YOLO 实现
    # from doclayout_yolo import DocLayoutYOLO
except ImportError:
    YOLO = None

# ========== 配置 ==========
app = FastAPI(title="DocLayout-YOLO Service", version="1.0.0")
logger = logging.getLogger(__name__)

# 模型路径（在 Docker 镜像中预先下载或挂载）
MODEL_PATHS = {
    "doclayout_yolo": "/models/doclayout_yolo.pt",
    "doclayout_yolo_cdla": "/models/doclayout_yolo_cdla.pt",
    "doclayout_yolo_docstructbench": "/models/doclayout_yolo_docstructbench.pt",
}

# 全局模型缓存
MODELS: Dict[str, Any] = {}


# ========== 模型加载 ==========
def load_model(model_name: str = "doclayout_yolo"):
    """
    加载 YOLO 模型（懒加载）。

    Args:
        model_name: 模型名称

    Returns:
        加载的模型实例
    """
    if model_name in MODELS:
        return MODELS[model_name]

    model_path = MODEL_PATHS.get(model_name)
    if not model_path:
        raise ValueError(f"Unknown model: {model_name}")

    logger.info(f"Loading model: {model_name} from {model_path}")

    # 实际加载逻辑（根据你的 YOLO 实现替换）
    if YOLO is not None:
        model = YOLO(model_path)
    else:
        # 伪代码：替换为你的实际加载方式
        raise NotImplementedError(
            "YOLO not installed. Install ultralytics or doclayout-yolo package."
        )

    MODELS[model_name] = model
    logger.info(f"Model loaded: {model_name}")
    return model


# ========== API 端点 ==========
@app.get("/")
async def root():
    """根路径，返回服务信息"""
    return {
        "service": "DocLayout-YOLO",
        "version": "1.0.0",
        "status": "running",
        "models": list(MODEL_PATHS.keys()),
    }


@app.get("/health")
async def health_check():
    """健康检查端点（Marker 会调用此端点确认服务可用）"""
    return {"status": "healthy", "service": "DocLayout-YOLO"}


@app.get("/ping")
async def ping():
    """备选健康检查端点"""
    return {"status": "ok"}


@app.get("/status")
async def status():
    """备选健康检查端点"""
    return {"status": "ready"}


@app.get("/models")
async def list_models():
    """列出可用的模型"""
    return {"models": list(MODEL_PATHS.keys())}


@app.post("/detect")
async def detect(
    file: UploadFile = File(...),
    model: str = Form("doclayout_yolo"),
    confidence: float = Form(0.25),
    iou: float = Form(0.45),
):
    """
    版面检测端点（主端点，Marker 优先尝试此端点）。

    Args:
        file: 上传的图像文件（PNG/JPEG/WEBP）
        model: 使用的模型名称
        confidence: 检测置信度阈值
        iou: NMS IOU 阈值

    Returns:
        检测结果 JSON，格式：
        {
            "detections": [
                {
                    "label": "text",
                    "bbox": [x1, y1, x2, y2],
                    "confidence": 0.95,
                    "polygon": [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
                },
                ...
            ]
        }
    """
    try:
        # 读取图像
        contents = await file.read()
        img = Image.open(BytesIO(contents))
        img_w, img_h = img.size

        # 加载模型
        yolo_model = load_model(model)

        # 运行推理
        # 实际推理逻辑（根据你的 YOLO 实现替换）
        results = yolo_model.predict(
            img,
            conf=confidence,
            iou=iou,
            verbose=False,
        )

        # 解析结果（根据你的 YOLO 输出格式调整）
        detections = []
        for result in results:
            # ultralytics YOLO 格式
            if hasattr(result, "boxes"):
                boxes = result.boxes
                for box in boxes:
                    # 提取坐标、置信度、类别
                    xyxy = box.xyxy[0].cpu().numpy()  # [x1, y1, x2, y2]
                    conf = float(box.conf[0].cpu().numpy())
                    cls_id = int(box.cls[0].cpu().numpy())

                    # 类别名映射（根据你的模型调整）
                    class_names = getattr(result, "names", {})
                    label = class_names.get(cls_id, str(cls_id))

                    x1, y1, x2, y2 = xyxy
                    detections.append({
                        "label": label,
                        "bbox": [float(x1), float(y1), float(x2), float(y2)],
                        "confidence": conf,
                        "polygon": [
                            [float(x1), float(y1)],
                            [float(x2), float(y1)],
                            [float(x2), float(y2)],
                            [float(x1), float(y2)],
                        ],
                    })

        return JSONResponse(content={"detections": detections})

    except Exception as e:
        logger.error(f"Detection failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/predict")
async def predict(
    file: UploadFile = File(...),
    model: str = Form("doclayout_yolo"),
    confidence: float = Form(0.25),
    iou: float = Form(0.45),
):
    """
    版面检测端点（备选端点名）。

    与 /detect 功能相同。
    """
    return await detect(file, model, confidence, iou)


@app.post("/inference")
async def inference(
    file: UploadFile = File(...),
    model: str = Form("doclayout_yolo"),
    confidence: float = Form(0.25),
    iou: float = Form(0.45),
):
    """
    版面检测端点（备选端点名）。

    与 /detect 功能相同。
    """
    return await detect(file, model, confidence, iou)


# ========== 启动服务 ==========
if __name__ == "__main__":
    # 本地测试启动
    # Docker 部署时使用: uvicorn yolo_service:app --host 0.0.0.0 --port 11900
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=11900,
        log_level="info",
    )


"""
========== Dockerfile 示例 ==========

FROM python:3.10-slim

WORKDIR /app

# 安装依赖
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn[standard] \
    pillow \
    numpy \
    torch \
    torchvision \
    ultralytics

# 复制模型文件（或在运行时挂载）
# COPY models/ /models/

# 复制服务代码
COPY yolo_docker_service_example.py /app/yolo_service.py

# 暴露端口
EXPOSE 11900

# 启动服务
CMD ["uvicorn", "yolo_service:app", "--host", "0.0.0.0", "--port", "11900"]


========== Docker 构建和运行 ==========

# 构建镜像
docker build -t doclayout-yolo-service:latest .

# 运行容器（挂载模型目录）
docker run -d \
  --name yolo-service \
  -p 11900:11900 \
  -v /path/to/models:/models \
  doclayout-yolo-service:latest

# 测试健康检查
curl http://localhost:11900/health

# 测试检测
curl -X POST http://localhost:11900/detect \
  -F "file=@test_page.png" \
  -F "model=doclayout_yolo" \
  -F "confidence=0.25"


========== Marker 配置示例 ==========

{
  "layout_backend": "yolo",
  "yolo_base_url": "http://localhost:11900",
  "yolo_model": "doclayout_yolo",
  "yolo_timeout": 60,
  "yolo_confidence_threshold": 0.25,
  "yolo_iou_threshold": 0.45
}

"""
