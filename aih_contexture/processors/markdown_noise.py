"""
Markdown Noise Removal Processor

清理 OCR 识别出的 Markdown 特殊符号噪音，防止与 Markdown 语法冲突。

设计理念：
- 在文本处理阶段清理噪音，而不是在渲染阶段
- 支持三个清理级别：基础、中等、激进
- 支持自定义符号列表
- 默认只清理行首符号，保护行中的合法内容
"""

import re
from typing import Annotated

from aih_contexture.processors import BaseProcessor
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document


class MarkdownNoiseRemovalProcessor(BaseProcessor):
    """
    清理文本中可能与 Markdown 语法冲突的 OCR 噪音符号。

    清理级别：
    - basic: 只清理 # 标题符号
    - medium: 清理 #, >, -, *, + 等常见符号
    - aggressive: 清理所有 Markdown 符号
    """

    block_types = (
        BlockTypes.Text,
        BlockTypes.TextInlineMath,
    )

    # 预定义的符号集
    BASIC_SYMBOLS = ["#"]
    MEDIUM_SYMBOLS = ["#", ">", "-", "*", "+"]
    AGGRESSIVE_SYMBOLS = ["#", ">", "-", "*", "+", "`", "~", "[", "]", "="]

    def __init__(self, config: dict = None):
        """初始化处理器，从 config 中提取配置"""
        super().__init__()

        # 从 config 中提取配置，如果没有则使用默认值
        if config:
            self.markdown_noise_cleaning_level = config.get("markdown_noise_cleaning_level", "basic")
            self.markdown_noise_line_start_only = config.get("markdown_noise_line_start_only", True)
            self.markdown_noise_custom_symbols = config.get("markdown_noise_custom_symbols", "")
        else:
            self.markdown_noise_cleaning_level = "basic"
            self.markdown_noise_line_start_only = True
            self.markdown_noise_custom_symbols = ""

    def __call__(self, document: Document):
        """处理文档中的所有文本块"""
        # 🔍 调试：确认处理器被调用
        print("=" * 80)
        print("🧹 MarkdownNoiseRemovalProcessor 被调用")
        print(f"   清理级别: {self.markdown_noise_cleaning_level}")
        print(f"   只清理行首: {self.markdown_noise_line_start_only}")
        print(f"   自定义符号: '{self.markdown_noise_custom_symbols}'")
        print("=" * 80)

        total_cleaned = 0

        for page in document.pages:
            for block in page.children:
                if block.block_type not in self.block_types:
                    continue

                if block.structure is None:
                    continue

                # 使用 structure_blocks 获取所有 Line 对象
                lines = block.structure_blocks(document)

                for line in lines:
                    if line is None or line.structure is None:
                        continue

                    # 使用 structure_blocks 获取所有 Span 对象
                    spans = line.structure_blocks(document)

                    for span in spans:
                        if not hasattr(span, 'text') or not span.text:
                            continue

                        original_text = span.text
                        cleaned_text = self.clean_text(original_text)

                        if cleaned_text != original_text:
                            print(f"🔧 清理文本:")
                            print(f"   原文: {original_text[:50]}...")
                            print(f"   清理后: {cleaned_text[:50]}...")
                            span.text = cleaned_text
                            total_cleaned += 1

        print(f"✅ 清理完成，共清理 {total_cleaned} 个文本片段")
        print("=" * 80)

    def clean_text(self, text: str) -> str:
        """清理文本中的 Markdown 噪音符号"""
        if not text:
            return text

        # 获取要清理的符号列表
        symbols = self._get_symbols_to_clean()

        if not symbols:
            return text

        # 🔍 调试：显示要清理的符号
        # print(f"   要清理的符号: {symbols}")

        # 按行处理
        lines = text.split('\n')
        cleaned_lines = []

        for line in lines:
            cleaned_line = self._clean_line(line, symbols)
            cleaned_lines.append(cleaned_line)

        return '\n'.join(cleaned_lines)

    def _get_symbols_to_clean(self):
        """根据配置获取要清理的符号列表"""
        # 优先使用自定义符号
        if self.markdown_noise_custom_symbols:
            symbols = [s.strip() for s in self.markdown_noise_custom_symbols.split(',') if s.strip()]
            return symbols

        # 根据清理级别返回预定义符号
        if self.markdown_noise_cleaning_level == "basic":
            return self.BASIC_SYMBOLS
        elif self.markdown_noise_cleaning_level == "medium":
            return self.MEDIUM_SYMBOLS
        elif self.markdown_noise_cleaning_level == "aggressive":
            return self.AGGRESSIVE_SYMBOLS
        else:
            return self.BASIC_SYMBOLS  # 默认

    def _clean_line(self, line: str, symbols: list) -> str:
        """清理单行文本"""
        if not line:
            return line

        cleaned_line = line

        if self.markdown_noise_line_start_only:
            # 只清理行首符号
            cleaned_line = self._clean_line_start(cleaned_line, symbols)
        else:
            # 清理所有位置的符号
            cleaned_line = self._clean_all_positions(cleaned_line, symbols)

        return cleaned_line

    def _clean_line_start(self, line: str, symbols: list) -> str:
        """只清理行首的符号"""
        # 构建正则表达式：匹配行首的符号 + 空格
        # 例如：^(\s*)[#>*\-+]+\s+

        # 转义特殊正则字符
        escaped_symbols = [re.escape(s) for s in symbols]
        pattern = r'^(\s*)[' + ''.join(escaped_symbols) + r']+\s+'

        # 替换：保留前导空格，移除符号和后面的空格
        cleaned = re.sub(pattern, r'\1', line)

        return cleaned

    def _clean_all_positions(self, line: str, symbols: list) -> str:
        """清理所有位置的符号"""
        cleaned = line

        # 先清理行首的符号 + 空格
        cleaned = self._clean_line_start(cleaned, symbols)

        # 再清理行中的符号（不带空格）
        for symbol in symbols:
            cleaned = cleaned.replace(symbol, '')

        return cleaned
