"""
DocLayout-YOLO 版面识别服务

通过 HTTP API 调用 DocLayout-YOLO Docker 服务进行版面识别。
支持多种 YOLO 模型变体，适用于不同类型的文档。
"""

import io
import time
from typing import Annotated, Dict, List, Optional

import requests
from PIL import Image

from aih_contexture.logger import get_logger
from aih_contexture.services.layout_base import (
    BaseLayoutService,
    LayoutBox,
    LayoutResult,
    SUPPORTED_LAYOUT_LABELS,
)

logger = get_logger()


# YOLO 标签到 Marker BlockTypes 的映射
DEFAULT_LABEL_MAPPING = {
    # DocLayout-YOLO 标准标签
    "text": "Text",
    "title": "SectionHeader",
    "list": "ListItem",
    "table": "Table",
    "figure": "Figure",
    "caption": "Caption",
    "header": "PageHeader",
    "footer": "PageFooter",
    "equation": "Equation",
    "code": "Code",
    "reference": "Text",
    "abstract": "Text",
    "author": "Text",

    # 通用别名
    "paragraph": "Text",
    "body": "Text",
    "image": "Picture",
    "picture": "Picture",
    "photo": "Picture",
    "chart": "Figure",
    "graph": "Figure",
    "formula": "Equation",
    "math": "Equation",
    "heading": "SectionHeader",
    "section": "SectionHeader",
    "footnote": "Footnote",
    "page_header": "PageHeader",
    "page_footer": "PageFooter",
    "page-header": "PageHeader",
    "page-footer": "PageFooter",
    "toc": "TableOfContents",
    "table_of_contents": "TableOfContents",
    "handwriting": "Handwriting",
    "form": "Form",
}


class YoloLayoutService(BaseLayoutService):
    """
    DocLayout-YOLO 版面识别服务。

    通过 HTTP API 调用 YOLO Docker 容器进行版面识别。
    Docker 镜像通常提供 /detect 或 /predict 端点。
    """

    # Docker 服务配置
    yolo_base_url: Annotated[
        str,
        "YOLO 服务 API 地址"
    ] = "http://localhost:11900"

    yolo_model: Annotated[
        str,
        "使用的模型名称"
    ] = "doclayout_yolo"

    yolo_timeout: Annotated[
        int,
        "HTTP 请求超时时间（秒）"
    ] = 60

    yolo_max_retries: Annotated[
        int,
        "最大重试次数"
    ] = 2

    # 检测参数
    yolo_confidence_threshold: Annotated[
        float,
        "检测置信度阈值"
    ] = 0.25

    yolo_iou_threshold: Annotated[
        float,
        "NMS IOU 阈值"
    ] = 0.45

    # 标签映射
    yolo_label_mapping: Annotated[
        Dict[str, str],
        "YOLO 标签到 Marker BlockTypes 的映射"
    ] = None

    def __init__(self, config: Optional[dict] = None):
        """初始化 YOLO 版面识别服务"""
        super().__init__(config)

        config = config or {}

        self.yolo_base_url = config.get("yolo_base_url", self.yolo_base_url)
        self.yolo_model = config.get("yolo_model", self.yolo_model)
        self.yolo_timeout = int(config.get("yolo_timeout", self.yolo_timeout))
        self.yolo_max_retries = int(config.get("yolo_max_retries", self.yolo_max_retries))

        if config.get("yolo_confidence_threshold") is not None:
            self.yolo_confidence_threshold = float(config["yolo_confidence_threshold"])
        if config.get("yolo_iou_threshold") is not None:
            self.yolo_iou_threshold = float(config["yolo_iou_threshold"])
        if config.get("confidence_threshold") is not None:
            self.confidence_threshold = float(config["confidence_threshold"])

        # 标签映射
        self.yolo_label_mapping = config.get("yolo_label_mapping") or DEFAULT_LABEL_MAPPING

        logger.info(
            f"[YoloLayoutService] Init: base_url={self.yolo_base_url}, "
            f"model={self.yolo_model}, timeout={self.yolo_timeout}"
        )

    def health_check(self) -> bool:
        """检查 YOLO 服务是否可用"""
        try:
            # 尝试多个常见的健康检查端点
            endpoints = ["/health", "/", "/status", "/ping"]
            for endpoint in endpoints:
                try:
                    resp = requests.get(
                        f"{self.yolo_base_url}{endpoint}",
                        timeout=5
                    )
                    if resp.status_code == 200:
                        logger.info(f"[YoloLayoutService] Health check passed: {endpoint}")
                        return True
                except Exception:
                    continue

            return False
        except Exception as e:
            logger.warning(f"[YoloLayoutService] Health check failed: {e}")
            return False

    def get_available_models(self) -> List[str]:
        """获取可用的模型列表"""
        try:
            resp = requests.get(
                f"{self.yolo_base_url}/models",
                timeout=self.yolo_timeout
            )
            if resp.status_code == 200:
                data = resp.json()
                return data.get("models", [])
            return []
        except Exception as e:
            logger.warning(f"[YoloLayoutService] Failed to get models: {e}")
            return []

    def detect_layout(
        self,
        images: List[Image.Image],
        batch_size: int = 1
    ) -> List[LayoutResult]:
        """
        对一批图像进行版面识别。

        Args:
            images: PIL Image 列表
            batch_size: 批处理大小

        Returns:
            LayoutResult 列表，与输入图像一一对应
        """
        results = []

        # 逐张处理（YOLO 通常单张处理更高效）
        for img in images:
            try:
                result = self._detect_single_image(img)
                results.append(result)
            except Exception as e:
                logger.error(f"[YoloLayoutService] Detection failed: {e}")
                # 返回空结果
                w, h = img.size
                results.append(LayoutResult(
                    image_bbox=[0, 0, w, h],
                    bboxes=[],
                    sliced=False
                ))

        return results

    def _detect_single_image(self, img: Image.Image) -> LayoutResult:
        """对单张图像进行版面识别"""
        original_size = img.size

        # 准备图像数据
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)

        files = {"file": ("image.png", buf.getvalue(), "image/png")}
        data = {
            "model": self.yolo_model,
            "confidence": self.yolo_confidence_threshold,
            "iou": self.yolo_iou_threshold,
        }

        # API 调用（带重试）
        last_error = None
        for attempt in range(self.yolo_max_retries + 1):
            try:
                # 尝试多个常见的检测端点
                endpoints = ["/detect", "/predict", "/inference", "/api/detect"]
                response_data = None

                for endpoint in endpoints:
                    try:
                        resp = requests.post(
                            f"{self.yolo_base_url}{endpoint}",
                            files=files,
                            data=data,
                            timeout=self.yolo_timeout
                        )
                        if resp.status_code == 200:
                            response_data = resp.json()
                            break
                        elif resp.status_code == 404:
                            continue
                        else:
                            resp.raise_for_status()
                    except requests.exceptions.HTTPError:
                        continue

                if response_data is None:
                    raise ValueError("No valid endpoint found")

                # 解析响应
                layout_boxes = self._parse_yolo_response(response_data, original_size)

                # 构建结果
                w, h = original_size
                result = LayoutResult(
                    image_bbox=[0, 0, w, h],
                    bboxes=layout_boxes,
                    sliced=False
                )

                return result

            except Exception as e:
                last_error = e
                logger.warning(
                    f"[YoloLayoutService] Attempt {attempt + 1} failed: {e}"
                )
                if attempt < self.yolo_max_retries:
                    time.sleep(1 * (attempt + 1))
                    continue

        # 所有重试失败
        logger.error(f"[YoloLayoutService] All retries failed: {last_error}")
        w, h = original_size
        return LayoutResult(
            image_bbox=[0, 0, w, h],
            bboxes=[],
            sliced=False
        )

    def _parse_yolo_response(
        self,
        data: dict,
        image_size: tuple
    ) -> List[LayoutBox]:
        """解析 YOLO 响应数据"""
        layout_boxes = []
        img_w, img_h = image_size

        # 支持多种响应格式
        detections = []

        # 格式 1: {"detections": [...]}
        if "detections" in data:
            detections = data["detections"]

        # 格式 2: {"predictions": [...]}
        elif "predictions" in data:
            detections = data["predictions"]

        # 格式 3: {"results": [...]}
        elif "results" in data:
            detections = data["results"]

        # 格式 4: {"boxes": [...], "labels": [...], "scores": [...]}
        elif "boxes" in data and "labels" in data:
            boxes = data.get("boxes", [])
            labels = data.get("labels", [])
            scores = data.get("scores", data.get("confidences", [1.0] * len(boxes)))
            for box, label, score in zip(boxes, labels, scores):
                detections.append({
                    "bbox": box,
                    "label": label,
                    "confidence": score
                })

        # 格式 5: 直接是列表
        elif isinstance(data, list):
            detections = data

        if not isinstance(detections, list):
            detections = []

        for idx, det in enumerate(detections):
            if not isinstance(det, dict):
                continue

            # 提取标签
            label = det.get("label", det.get("class", det.get("name", "Text")))
            if isinstance(label, int):
                # 如果是类别 ID，尝试从 class_names 获取
                class_names = det.get("class_names", data.get("class_names", {}))
                label = class_names.get(label, str(label))

            # 提取置信度
            confidence = det.get("confidence", det.get("score", det.get("prob", 0.9)))

            # 提取边界框
            bbox = det.get("bbox", det.get("box", det.get("bounding_box", None)))
            if bbox is None:
                # 尝试从 x, y, w, h 或 x1, y1, x2, y2 提取
                if all(k in det for k in ["x", "y", "w", "h"]):
                    x, y, w, h = det["x"], det["y"], det["w"], det["h"]
                    bbox = [x, y, x + w, y + h]
                elif all(k in det for k in ["x1", "y1", "x2", "y2"]):
                    bbox = [det["x1"], det["y1"], det["x2"], det["y2"]]
                elif all(k in det for k in ["xmin", "ymin", "xmax", "ymax"]):
                    bbox = [det["xmin"], det["ymin"], det["xmax"], det["ymax"]]
                else:
                    continue

            # 规范化边界框格式
            if len(bbox) == 4:
                x1, y1, x2, y2 = bbox

                # 处理归一化坐标（0-1 范围）
                if max(bbox) <= 1.0:
                    x1, y1, x2, y2 = x1 * img_w, y1 * img_h, x2 * img_w, y2 * img_h

                # 确保坐标在图像范围内
                x1 = max(0, min(img_w, x1))
                y1 = max(0, min(img_h, y1))
                x2 = max(0, min(img_w, x2))
                y2 = max(0, min(img_h, y2))

                # 转换为 polygon 格式
                polygon = [
                    [x1, y1],
                    [x2, y1],
                    [x2, y2],
                    [x1, y2]
                ]
            else:
                continue

            # 标签映射
            label_lower = str(label).lower().strip()
            normalized_label = self.yolo_label_mapping.get(label_lower)
            if normalized_label is None:
                normalized_label = self.normalize_label(label)
            if normalized_label not in SUPPORTED_LAYOUT_LABELS:
                normalized_label = "Text"

            # 过滤低置信度
            if confidence < self.yolo_confidence_threshold:
                continue

            layout_boxes.append(LayoutBox(
                label=normalized_label,
                position=idx,
                top_k={normalized_label: float(confidence)},
                polygon=polygon
            ))

        # 按位置排序（从上到下，从左到右）
        layout_boxes.sort(key=lambda b: (b.polygon[0][1], b.polygon[0][0]))

        # 重新分配 position
        for i, box in enumerate(layout_boxes):
            box.position = i

        return layout_boxes

    def normalize_label(self, label: str) -> str:
        """将 YOLO 标签规范化为 Marker BlockTypes"""
        # 先检查映射表
        label_lower = str(label).lower().strip()
        if label_lower in self.yolo_label_mapping:
            return self.yolo_label_mapping[label_lower]

        # 使用基类的规范化
        return super().normalize_label(label)

# Backward compatibility alias
DocLayoutYoloService = YoloLayoutService
