from aih_contexture.schema import BlockTypes
from aih_contexture.schema.blocks import Block


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
        position = self.get_internal_metadata("position_type") or "unknown"

        # 添加语义化的 HTML 属性
        return f'<aside class="marginal-annotation" data-subtype="{subtype}" data-position="{position}">{template}</aside>'
