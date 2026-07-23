from aih_contexture.schema import BlockTypes
from aih_contexture.schema.blocks import Block


def _infer_position_from_geometry(block: Block, document) -> str:
    page = document.get_page(block.page_id) if document is not None else None
    page_polygon = getattr(page, "polygon", None)
    block_polygon = getattr(block, "polygon", None)
    if page_polygon is None or block_polygon is None:
        return "unknown"

    page_x0, page_y0, page_x1, page_y1 = page_polygon.bbox
    x0, y0, x1, y1 = block_polygon.bbox
    page_width = max(float(page_x1) - float(page_x0), 1.0)
    page_height = max(float(page_y1) - float(page_y0), 1.0)
    center_x = ((float(x0) + float(x1)) / 2.0 - float(page_x0)) / page_width
    center_y = ((float(y0) + float(y1)) / 2.0 - float(page_y0)) / page_height

    if center_x <= 0.22:
        return "left_margin"
    if center_x >= 0.78:
        return "right_margin"
    if center_y <= 0.12:
        return "top_margin"
    if center_y >= 0.88:
        return "bottom_margin"
    return "unknown"


class MarginalAnnotation(Block):
    """
    边码/页边注块类型。

    涵盖内容：
    - 中文古籍版心（书名、卷次、叶码）
    - 鱼尾装饰符
    - Stephanus/Bekker 页边编码
    - 行号（Critical Edition）
    - 眉批/批注
    - 书耳

    元数据字段（通过 _metadata 存储）：
    - marginal_subtype: 细分类型（版心叶码/行号/Stephanus编码/Bekker编码/书耳/眉批/鱼尾）
    - position_type: 位置类型（left_margin/right_margin/top_margin/bottom_margin/vertical_center）
    """
    block_type: BlockTypes = BlockTypes.MarginalAnnotation
    block_description: str = "Marginal annotations including page numbers, line numbers, and scholarly references."

    def assemble_html(self, document, child_blocks, parent_structure, block_config=None):
        if self.ignore_for_output:
            return ""

        template = super().assemble_html(document, child_blocks, parent_structure, block_config)

        # 获取细分类型
        subtype = self.get_internal_metadata("marginal_subtype") or "unknown"
        position = self.get_internal_metadata("position_type") or _infer_position_from_geometry(self, document)

        # 添加语义化的 HTML 属性
        return f'<aside class="marginal-annotation" data-subtype="{subtype}" data-position="{position}">{template}</aside>'
