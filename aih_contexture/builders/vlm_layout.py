"""
VLM 版面识别 Builder

使用 VLM (Vision Language Model) 进行版面识别，复用 LayoutBuilder 的通用方法。
"""

from typing import Annotated, List, Optional

from aih_contexture.builders import BaseBuilder
from aih_contexture.builders.layout import LayoutBuilder
from aih_contexture.providers.pdf import PdfProvider
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.services.layout_vlm import VlmLayoutService
from aih_contexture.services.layout_base import LayoutResult, LayoutBox
from aih_contexture.logger import get_logger

logger = get_logger()


class VlmLayoutBuilder(BaseBuilder):
    """
    使用 VLM 进行版面识别的 Builder。

    通过 VLM 服务分析页面图像，识别文档版面结构，
    然后使用 LayoutBuilder 的通用方法将结果添加到文档中。
    """

    # 批处理大小（VLM 通常逐页处理）
    vlm_layout_batch_size: Annotated[
        int,
        "VLM 版面识别批处理大小"
    ] = 1

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
        vlm_layout_service: VlmLayoutService,
        config: Optional[dict] = None
    ):
        """
        初始化 VLM 版面识别 Builder。

        Args:
            vlm_layout_service: VLM 版面识别服务实例
            config: 配置字典
        """
        super().__init__(config)

        self.vlm_layout_service = vlm_layout_service

        # 从 config 读取配置
        if isinstance(config, dict):
            if config.get("vlm_layout_batch_size") is not None:
                self.vlm_layout_batch_size = int(config["vlm_layout_batch_size"])
            if config.get("force_layout_block") is not None:
                self.force_layout_block = config["force_layout_block"]
            if config.get("max_expand_frac") is not None:
                self.max_expand_frac = float(config["max_expand_frac"])
            if config.get("disable_tqdm") is not None:
                self.disable_tqdm = bool(config["disable_tqdm"])

        # 创建一个临时的 LayoutBuilder 实例来复用其方法
        # 注意：layout_model 设为 None，因为我们不会使用 surya_layout
        self._layout_helper = _LayoutHelper(config=config)
        self._layout_helper.expand_block_types = self.expand_block_types
        self._layout_helper.max_expand_frac = self.max_expand_frac

        logger.info(
            f"[VlmLayoutBuilder] Init: batch_size={self.vlm_layout_batch_size}, "
            f"force_layout_block={self.force_layout_block}"
        )

    def __call__(self, document: Document, provider: PdfProvider):
        """
        执行版面识别。

        Args:
            document: 文档对象
            provider: PDF 提供者
        """
        logger.info(f"[VlmLayoutBuilder] Processing {len(document.pages)} pages")

        if self.force_layout_block is not None:
            # 强制版面模式
            logger.info(f"[VlmLayoutBuilder] Using forced layout: {self.force_layout_block}")
            layout_results = self._forced_layout(document.pages)
        else:
            # VLM 版面识别
            layout_results = self._vlm_layout(document.pages)

        # 将版面结果添加到页面
        self._layout_helper.add_blocks_to_pages(document.pages, layout_results)

        # 扩展特定块类型的边界
        self._layout_helper.expand_layout_blocks(document)

        logger.info(f"[VlmLayoutBuilder] Completed processing {len(document.pages)} pages")

    def _vlm_layout(self, pages: List[PageGroup]) -> List[LayoutResult]:
        """
        使用 VLM 进行版面识别。

        Args:
            pages: 页面列表

        Returns:
            版面识别结果列表
        """
        # 获取低分辨率图像
        images = [p.get_image(highres=False) for p in pages]

        logger.info(f"[VlmLayoutBuilder] Sending {len(images)} images to VLM service")

        # 调用 VLM 服务
        layout_results = self.vlm_layout_service.detect_layout(
            images,
            batch_size=self.vlm_layout_batch_size
        )

        # 统计识别结果
        total_boxes = sum(len(r.bboxes) for r in layout_results)
        logger.info(f"[VlmLayoutBuilder] Detected {total_boxes} layout boxes in {len(pages)} pages")

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


class _LayoutHelper(BaseBuilder):
    """
    版面处理辅助类。

    封装 LayoutBuilder 的通用方法，供 VlmLayoutBuilder 复用。
    这些方法负责将版面识别结果转换为文档块并添加到页面中。
    """

    expand_block_types: List[BlockTypes] = [
        BlockTypes.Picture,
        BlockTypes.Figure,
        BlockTypes.ComplexRegion,
    ]
    max_expand_frac: float = 0.05

    def __init__(self, config: Optional[dict] = None):
        super().__init__(config)

        if isinstance(config, dict):
            if config.get("expand_block_types") is not None:
                # 支持字符串列表转换
                block_types = config["expand_block_types"]
                if isinstance(block_types, list) and block_types:
                    if isinstance(block_types[0], str):
                        self.expand_block_types = [
                            BlockTypes[bt] for bt in block_types
                            if bt in BlockTypes.__members__
                        ]
                    else:
                        self.expand_block_types = block_types
            if config.get("max_expand_frac") is not None:
                self.max_expand_frac = float(config["max_expand_frac"])

    def add_blocks_to_pages(
        self,
        pages: List[PageGroup],
        layout_results: List[LayoutResult]
    ):
        """
        将版面识别结果添加到页面中。

        这是从 LayoutBuilder 复制的核心逻辑，用于处理统一的 LayoutResult 格式。

        Args:
            pages: 页面列表
            layout_results: 版面识别结果列表（与页面一一对应）
        """
        from aih_contexture.schema.polygon import PolygonBox
        from aih_contexture.schema.registry import get_block_class

        for page, layout_result in zip(pages, layout_results):
            # 获取版面模型的图像尺寸和页面实际尺寸
            layout_page_size = PolygonBox.from_bbox(layout_result.image_bbox).size
            provider_page_size = page.polygon.size

            # 标记页面是否被切片
            page.layout_sliced = layout_result.sliced

            # 按阅读顺序处理每个版面框
            for bbox in sorted(layout_result.bboxes, key=lambda x: x.position):
                # 获取块类型对应的类
                try:
                    block_cls = get_block_class(BlockTypes[bbox.label])
                except (KeyError, ValueError):
                    # 未知标签，使用 Text
                    block_cls = get_block_class(BlockTypes.Text)

                # 创建块对象
                layout_block = page.add_block(
                    block_cls,
                    PolygonBox(polygon=bbox.polygon)
                )

                # 重新缩放到页面尺寸
                layout_block.polygon = layout_block.polygon.rescale(
                    layout_page_size, provider_page_size
                ).fit_to_bounds((0, 0, *provider_page_size))

                # 转换置信度信息
                layout_block.top_k = {
                    BlockTypes[label]: prob
                    for (label, prob) in bbox.top_k.items()
                    if label in BlockTypes.__members__
                }

                # 添加到页面结构
                page.add_structure(layout_block)

            # 确保页面有非空结构
            if page.structure is None:
                page.structure = []
            if page.children is None:
                page.children = []

    def expand_layout_blocks(self, document: Document):
        """
        扩展特定块类型的边界。

        对于 Picture、Figure 等块类型，适当扩展边界以捕获可能遗漏的区域。

        Args:
            document: 文档对象
        """
        for page in document.pages:
            # 收集页面上所有的块
            page_blocks = [document.get_block(bid) for bid in page.structure]
            page_size = page.polygon.size

            for block_id in page.structure:
                block = document.get_block(block_id)
                if block.block_type in self.expand_block_types:
                    other_blocks = [b for b in page_blocks if b != block]
                    if not other_blocks:
                        # 没有其他块，直接扩展
                        block.polygon = block.polygon.expand(
                            self.max_expand_frac, self.max_expand_frac
                        ).fit_to_bounds((0, 0, *page_size))
                        continue

                    # 计算与其他块的最小间隙
                    min_gap = min(
                        block.polygon.minimum_gap(other.polygon)
                        for other in other_blocks
                    )
                    if min_gap <= 0:
                        continue

                    # 计算扩展比例
                    x_expand_frac = (
                        min_gap / block.polygon.width if block.polygon.width > 0 else 0
                    )
                    y_expand_frac = (
                        min_gap / block.polygon.height if block.polygon.height > 0 else 0
                    )

                    # 扩展边界
                    block.polygon = block.polygon.expand(
                        min(self.max_expand_frac, x_expand_frac),
                        min(self.max_expand_frac, y_expand_frac),
                    ).fit_to_bounds((0, 0, *page_size))
