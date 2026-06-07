"""
版面识别服务基类和统一数据结构

定义可插拔版面识别后端的接口规范，所有版面识别服务都应继承 BaseLayoutService。
数据结构 LayoutBox 和 LayoutResult 兼容 Surya 的输出格式。
"""

from typing import Annotated, List, Dict, Any, Optional
from PIL import Image
from pydantic import BaseModel

from aih_contexture.services import BaseService


class LayoutBox(BaseModel):
    """
    统一版面框格式，兼容 Surya 的 LayoutBox。

    Attributes:
        label: BlockTypes 枚举名，如 "Text", "Figure", "Table", "SectionHeader" 等
        position: 阅读顺序位置（0 开始）
        top_k: 各标签的置信度字典，如 {"Text": 0.95, "Caption": 0.03}
        polygon: 四角坐标 [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
    """
    label: str
    position: int
    top_k: Dict[str, float]
    polygon: List[List[float]]

    class Config:
        # 允许任意类型（兼容 surya 的 LayoutBox）
        arbitrary_types_allowed = True


class LayoutResult(BaseModel):
    """
    统一版面识别结果格式，兼容 Surya 的 LayoutResult。

    Attributes:
        image_bbox: 图像边界框 [x0, y0, x1, y1]
        bboxes: 识别出的版面框列表
        sliced: 图像是否被切片处理（可能影响顺序准确性）
    """
    image_bbox: List[float]
    bboxes: List[LayoutBox]
    sliced: bool = False

    class Config:
        arbitrary_types_allowed = True


# 支持的 BlockTypes 标签列表（与 marker/schema/__init__.py 中的 BlockTypes 枚举对应）
SUPPORTED_LAYOUT_LABELS = [
    "Text",
    "Caption",
    "Code",
    "Figure",
    "Footnote",
    "Form",
    "Equation",
    "Handwriting",
    "TextInlineMath",
    "ListItem",
    "PageFooter",
    "PageHeader",
    "Picture",
    "SectionHeader",
    "Table",
    "TableOfContents",
    "ComplexRegion",
]


class BaseLayoutService(BaseService):
    """
    版面识别服务基类。

    所有版面识别后端（VLM、MinerU/Paddle adapter 等）都应继承此类并实现 detect_layout 方法。
    """

    # 服务超时时间（秒）
    layout_timeout: Annotated[
        int,
        "版面识别服务超时时间（秒）"
    ] = 60

    # 最大重试次数
    layout_max_retries: Annotated[
        int,
        "版面识别失败时的最大重试次数"
    ] = 2

    # 置信度阈值
    confidence_threshold: Annotated[
        float,
        "版面框的最小置信度阈值，低于此值的框将被过滤"
    ] = 0.3

    def detect_layout(
        self,
        images: List[Image.Image],
        batch_size: int = 1
    ) -> List[LayoutResult]:
        """
        对一批图像进行版面识别。

        Args:
            images: PIL Image 列表（通常是低分辨率页面图像）
            batch_size: 批处理大小

        Returns:
            LayoutResult 列表，与输入图像一一对应

        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError("子类必须实现 detect_layout 方法")

    def health_check(self) -> bool:
        """
        检查服务是否可用。

        Returns:
            True 表示服务正常，False 表示服务不可用
        """
        return True

    def normalize_label(self, label: str) -> str:
        """
        将外部标签规范化为 Marker 的 BlockTypes 标签。

        子类可以覆盖此方法以实现自定义标签映射。

        Args:
            label: 原始标签

        Returns:
            规范化后的标签名
        """
        # 默认：首字母大写
        normalized = label.strip().title().replace(" ", "").replace("_", "")

        # 常见别名映射
        label_aliases = {
            "Title": "SectionHeader",
            "Header": "PageHeader",
            "Footer": "PageFooter",
            "Image": "Picture",
            "Math": "Equation",
            "Formula": "Equation",
            "List": "ListItem",
            "Paragraph": "Text",
            "Body": "Text",
        }

        return label_aliases.get(normalized, normalized)

    def filter_by_confidence(
        self,
        layout_result: LayoutResult,
        threshold: Optional[float] = None
    ) -> LayoutResult:
        """
        根据置信度阈值过滤版面框。

        Args:
            layout_result: 原始版面识别结果
            threshold: 置信度阈值，默认使用 self.confidence_threshold

        Returns:
            过滤后的 LayoutResult
        """
        if threshold is None:
            threshold = self.confidence_threshold

        filtered_bboxes = []
        for bbox in layout_result.bboxes:
            # 获取最高置信度
            max_confidence = max(bbox.top_k.values()) if bbox.top_k else 1.0
            if max_confidence >= threshold:
                filtered_bboxes.append(bbox)

        # 重新分配 position
        for i, bbox in enumerate(filtered_bboxes):
            bbox.position = i

        return LayoutResult(
            image_bbox=layout_result.image_bbox,
            bboxes=filtered_bboxes,
            sliced=layout_result.sliced
        )

    def validate_labels(self, layout_result: LayoutResult) -> LayoutResult:
        """
        验证并修正标签，确保所有标签都是有效的 BlockTypes。

        Args:
            layout_result: 原始版面识别结果

        Returns:
            标签修正后的 LayoutResult
        """
        validated_bboxes = []
        for bbox in layout_result.bboxes:
            normalized_label = self.normalize_label(bbox.label)
            if normalized_label in SUPPORTED_LAYOUT_LABELS:
                # 更新标签和 top_k
                new_top_k = {}
                for k, v in bbox.top_k.items():
                    norm_k = self.normalize_label(k)
                    if norm_k in SUPPORTED_LAYOUT_LABELS:
                        new_top_k[norm_k] = v

                if not new_top_k:
                    new_top_k = {normalized_label: 1.0}

                validated_bboxes.append(LayoutBox(
                    label=normalized_label,
                    position=bbox.position,
                    top_k=new_top_k,
                    polygon=bbox.polygon
                ))
            # 无效标签的框被丢弃

        # 重新分配 position
        for i, bbox in enumerate(validated_bboxes):
            bbox.position = i

        return LayoutResult(
            image_bbox=layout_result.image_bbox,
            bboxes=validated_bboxes,
            sliced=layout_result.sliced
        )
