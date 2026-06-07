from aih_contexture.schema import BlockTypes
from aih_contexture.schema.blocks import Block


class InlineAnnotation(Block):
    """
    行内小字注块类型。

    涵盖内容：
    - 双行小字
    - 夹注
    - 割注（割裂原文的注释）
    - 括号包裹的短注释

    元数据字段（通过 _metadata 存储）：
    - inline_subtype: 细分类型（双行小字/夹注/割注/括号注）
    - font_size_ratio: 字体大小与主文本的比例
    - is_parenthetical: 是否为括号包裹
    """
    block_type: BlockTypes = BlockTypes.InlineAnnotation
    block_description: str = "Inline annotations including interlinear notes and small-text annotations."

    def assemble_html(self, document, child_blocks, parent_structure, block_config=None):
        if self.ignore_for_output:
            return ""

        template = super().assemble_html(document, child_blocks, parent_structure, block_config)

        # 获取细分类型
        subtype = self.get_internal_metadata("inline_subtype") or "unknown"
        font_ratio = self.get_internal_metadata("font_size_ratio") or 1.0

        # 添加语义化的 HTML 属性
        return f'<span class="inline-annotation" data-subtype="{subtype}" data-font-ratio="{font_ratio:.2f}">{template}</span>'
