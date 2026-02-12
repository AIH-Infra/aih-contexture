"""
智能降噪处理器

使用 LLM 识别并移除 OCR 产生的噪音字符
"""

from typing import Annotated, Dict, List, Optional, Tuple

from pydantic import BaseModel

from aih_contexture.processors.llm import BaseLLMSimpleBlockProcessor
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.logger import get_logger

logger = get_logger()


class NoiseRemovalSchema(BaseModel):
    """噪音移除响应模式"""
    cleaned_text: str
    removed_chars: List[str]
    confidence: int


class LLMNoiseRemovalProcessor(BaseLLMSimpleBlockProcessor):
    """
    智能降噪处理器

    使用 LLM 识别并移除 OCR 产生的噪音字符
    """

    block_types: Tuple[BlockTypes] = (
        BlockTypes.Text,
        BlockTypes.TextInlineMath,
    )

    # 文档级分析：读取前 N 页
    doc_analysis_pages: Annotated[
        int,
        "文档级分析读取的页数"
    ] = 5

    # 噪音移除提示词
    noise_removal_prompt: Annotated[
        str,
        "噪音移除提示词"
    ] = """你是 OCR 噪音识别专家。

文档类型：{document_type}
常见合法符号：{common_symbols}

请分析以下文本，识别并移除 OCR 产生的噪音字符：

{text}

噪音字符特征：
1. 随机特殊符号（不符合文档类型）
2. 孤立的无意义字符
3. 明显的识别错误（如 l 误识别为 1）

请输出：
1. cleaned_text: 清理后的文本
2. removed_chars: 移除的字符列表
3. confidence: 置信度（1-5）
"""

    def __init__(self, llm_service, config=None):
        super().__init__(llm_service, config)
        self.document_type = None
        self.common_symbols = None

    def __call__(self, document: Document):
        """
        处理文档，移除噪音字符

        Args:
            document: 文档对象
        """
        if not self.use_llm or not self.llm_service:
            logger.info("[LLMNoiseRemovalProcessor] ❌ Disabled (no LLM service)")
            return

        logger.info(f"[LLMNoiseRemovalProcessor] ✅ Enabled, processing {len(document.pages)} pages")

        # 第一步：文档级分析
        self.document_type, self.common_symbols = self._analyze_document(document)
        logger.info(f"[LLMNoiseRemovalProcessor] Document type: {self.document_type}")
        logger.info(f"[LLMNoiseRemovalProcessor] Common symbols: {self.common_symbols}")

        # 第二步：页面级过滤
        super().__call__(document)

    def _analyze_document(self, document: Document) -> Tuple[str, List[str]]:
        """
        分析文档类型和常见符号

        Args:
            document: 文档对象

        Returns:
            (文档类型, 常见符号列表)
        """
        # 取前 N 页（跳过空白页）
        sample_pages = []
        for page in document.pages[:10]:  # 最多检查前 10 页
            if len(sample_pages) >= self.doc_analysis_pages:
                break
            # 跳过空白页
            if self._is_blank_page(page, document):
                continue
            sample_pages.append(page)

        if not sample_pages:
            return "unknown", []

        # 分析文档类型
        doc_type = self._classify_document_type(sample_pages, document)

        # 提取常见符号
        common_symbols = self._extract_common_symbols(sample_pages, document)

        return doc_type, common_symbols

    def _is_blank_page(self, page, document: Document) -> bool:
        """判断是否为空白页"""
        if not page.structure:
            return True

        # 检查是否有文本内容
        text_blocks = page.contained_blocks(document, (BlockTypes.Text, BlockTypes.TextInlineMath))
        if not text_blocks:
            return True

        # 检查文本长度
        total_text_length = sum(len(block.raw_text(document)) for block in text_blocks)
        return total_text_length < 50  # 少于 50 个字符认为是空白页

    def _classify_document_type(self, sample_pages: List, document: Document) -> str:
        """
        分类文档类型

        Args:
            sample_pages: 样本页面列表
            document: 文档对象

        Returns:
            文档类型字符串
        """
        # 简单的启发式分类
        # 可以根据需要扩展更复杂的分类逻辑

        # 检查是否包含大量数学公式
        equation_count = 0
        for page in sample_pages:
            equations = page.contained_blocks(document, (BlockTypes.Equation, BlockTypes.InlineMath))
            equation_count += len(equations)

        if equation_count > 10:
            return "academic_math"

        # 检查是否包含代码块
        code_count = 0
        for page in sample_pages:
            code_blocks = page.contained_blocks(document, (BlockTypes.Code,))
            code_count += len(code_blocks)

        if code_count > 5:
            return "technical"

        # 检查是否包含中文
        chinese_char_count = 0
        total_char_count = 0
        for page in sample_pages:
            text_blocks = page.contained_blocks(document, (BlockTypes.Text, BlockTypes.TextInlineMath))
            for block in text_blocks:
                text = block.raw_text(document)
                total_char_count += len(text)
                chinese_char_count += sum(1 for char in text if '\u4e00' <= char <= '\u9fff')

        if total_char_count > 0 and chinese_char_count / total_char_count > 0.3:
            return "chinese_document"

        return "general"

    def _extract_common_symbols(self, sample_pages: List, document: Document) -> List[str]:
        """
        提取常见符号

        Args:
            sample_pages: 样本页面列表
            document: 文档对象

        Returns:
            常见符号列表
        """
        from collections import Counter
        import re

        # 提取所有特殊符号
        symbols = []
        for page in sample_pages:
            text_blocks = page.contained_blocks(document, (BlockTypes.Text, BlockTypes.TextInlineMath))
            for block in text_blocks:
                text = block.raw_text(document)
                # 提取非字母数字字符
                special_chars = re.findall(r'[^\w\s]', text, re.UNICODE)
                symbols.extend(special_chars)

        # 统计频率
        symbol_counts = Counter(symbols)

        # 返回最常见的 10 个符号
        common = [symbol for symbol, count in symbol_counts.most_common(10)]
        return common

    def process_block(self, document: Document, block, page):
        """
        处理单个块

        Args:
            document: 文档对象
            block: 块对象
            page: 页面对象
        """
        text = block.raw_text(document)
        if not text or len(text) < 10:
            return

        # 构建提示词
        prompt = self.noise_removal_prompt.format(
            document_type=self.document_type or "unknown",
            common_symbols=", ".join(self.common_symbols) if self.common_symbols else "N/A",
            text=text
        )

        # 调用 LLM
        try:
            response = self.llm_service(prompt, None, block, NoiseRemovalSchema)

            if response and "cleaned_text" in response:
                cleaned_text = response["cleaned_text"]
                removed_chars = response.get("removed_chars", [])
                confidence = response.get("confidence", 3)

                # 如果置信度足够高且确实移除了字符，更新块内容
                if confidence >= 3 and removed_chars:
                    logger.info(f"[LLMNoiseRemovalProcessor] Removed {len(removed_chars)} noise chars from block")
                    # 更新块的文本内容
                    # 注意：这里需要根据实际的块结构来更新
                    # 简化处理：更新 block 的 text 属性（如果存在）
                    if hasattr(block, "text"):
                        block.text = cleaned_text

        except Exception as e:
            logger.error(f"[LLMNoiseRemovalProcessor] Error processing block: {e}")
            block.update_metadata(llm_error_count=1)
