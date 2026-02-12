"""
YOLO 版面识别 Builder

使用 DocLayout-YOLO 进行版面识别，通过 Docker 服务调用。
"""

from typing import Annotated, List, Optional

from aih_contexture.builders import BaseBuilder
from aih_contexture.builders.vlm_layout import _LayoutHelper
from aih_contexture.providers.pdf import PdfProvider
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.services.layout_yolo import YoloLayoutService
from aih_contexture.services.layout_base import LayoutResult, LayoutBox
from aih_contexture.logger import get_logger

logger = get_logger()


class YoloLayoutBuilder(BaseBuilder):
    """
    使用 DocLayout-YOLO 进行版面识别的 Builder。

    通过 YOLO Docker 服务分析页面图像，识别文档版面结构，
    然后使用通用方法将结果添加到文档中。
    """

    # 批处理大小
    yolo_layout_batch_size: Annotated[
        int,
        "YOLO 版面识别批处理大小"
    ] = 4

    # 强制版面类型（跳过版面识别）
    force_layout_block: Annotated[
        str,
        "强制所有页面使用指定的块类型，跳过版面识别"
    ] = None

    # 需要扩展边界的块类型
    expand_block_types: Annotated[
        List[BlockTypes],
        "需要扩展边界的块类型列表"
    ] = [
        BlockTypes.Picture,
        BlockTypes.Figure,
        BlockTypes.ComplexRegion,
    ]

    # 最大扩展比例
    max_expand_frac: Annotated[
        float,
        "版面框边界的最大扩展比例"
    ] = 0.05

    # 禁用进度条
    disable_tqdm: Annotated[
        bool,
        "禁用进度条显示"
    ] = False

    def __init__(
        self,
        yolo_layout_service: YoloLayoutService,
        config: Optional[dict] = None
    ):
        """
        初始化 YOLO 版面识别 Builder。

        Args:
            yolo_layout_service: YOLO 版面识别服务实例
            config: 配置字典
        """
        super().__init__(config)

        self.yolo_layout_service = yolo_layout_service

        # 从 config 读取配置
        if isinstance(config, dict):
            if config.get("yolo_layout_batch_size") is not None:
                self.yolo_layout_batch_size = int(config["yolo_layout_batch_size"])
            if config.get("force_layout_block") is not None:
                self.force_layout_block = config["force_layout_block"]
            if config.get("max_expand_frac") is not None:
                self.max_expand_frac = float(config["max_expand_frac"])
            if config.get("disable_tqdm") is not None:
                self.disable_tqdm = bool(config["disable_tqdm"])

        # 创建版面处理辅助类
        self._layout_helper = _LayoutHelper(config=config)
        self._layout_helper.expand_block_types = self.expand_block_types
        self._layout_helper.max_expand_frac = self.max_expand_frac

        logger.info(
            f"[YoloLayoutBuilder] Init: batch_size={self.yolo_layout_batch_size}, "
            f"force_layout_block={self.force_layout_block}"
        )

    def __call__(self, document: Document, provider: PdfProvider):
        """
        执行版面识别。

        Args:
            document: 文档对象
            provider: PDF 提供者
        """
        logger.info(f"[YoloLayoutBuilder] Processing {len(document.pages)} pages")

        if self.force_layout_block is not None:
            # 强制版面模式
            logger.info(f"[YoloLayoutBuilder] Using forced layout: {self.force_layout_block}")
            layout_results = self._forced_layout(document.pages)
        else:
            # YOLO 版面识别
            layout_results = self._yolo_layout(document.pages)

        # 将版面结果添加到页面
        self._layout_helper.add_blocks_to_pages(document.pages, layout_results)

        # 扩展特定块类型的边界
        self._layout_helper.expand_layout_blocks(document)

        logger.info(f"[YoloLayoutBuilder] Completed processing {len(document.pages)} pages")

    def _yolo_layout(self, pages: List[PageGroup]) -> List[LayoutResult]:
        """
        使用 YOLO 进行版面识别。

        Args:
            pages: 页面列表

        Returns:
            版面识别结果列表
        """
        # 获取低分辨率图像
        images = [p.get_image(highres=False) for p in pages]

        logger.info(f"[YoloLayoutBuilder] Sending {len(images)} images to YOLO service")

        # 分批处理
        layout_results = []
        batch_size = self.yolo_layout_batch_size

        for i in range(0, len(images), batch_size):
            batch_images = images[i:i + batch_size]
            batch_results = self.yolo_layout_service.detect_layout(
                batch_images,
                batch_size=batch_size
            )
            layout_results.extend(batch_results)

            if len(images) > batch_size:
                logger.info(
                    f"[YoloLayoutBuilder] Processed batch {i // batch_size + 1}/"
                    f"{(len(images) + batch_size - 1) // batch_size}"
                )

        # 统计识别结果
        total_boxes = sum(len(r.bboxes) for r in layout_results)
        logger.info(f"[YoloLayoutBuilder] Detected {total_boxes} layout boxes in {len(pages)} pages")

        return layout_results

    def _forced_layout(self, pages: List[PageGroup]) -> List[LayoutResult]:
        """
        强制版面模式：将整个页面作为单个指定类型的块。

        Args:
            pages: 页面列表

        Returns:
            版面识别结果列表
        """
        layout_results = []
        for page in pages:
            layout_results.append(
                LayoutResult(
                    image_bbox=page.polygon.bbox,
                    bboxes=[
                        LayoutBox(
                            label=self.force_layout_block,
                            position=0,
                            top_k={self.force_layout_block: 1.0},
                            polygon=page.polygon.polygon,
                        ),
                    ],
                    sliced=False,
                )
            )
        return layout_results
