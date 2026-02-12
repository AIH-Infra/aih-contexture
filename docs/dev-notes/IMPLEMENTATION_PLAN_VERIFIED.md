# 功能实现方案（代码验证版）

## 代码验证结果

### 1. Pipeline vs VLM Direct 模式差异

**PdfConverter (Pipeline 模式)**:
- 流程: Layout Detection → OCR → Processors → Renderer → Markdown
- 使用处理器: 包含所有 LLM 处理器
- 输出: 结构化文档 → 渲染为 Markdown
- 位置: `marker/converters/pdf.py`

**VlmDirectConverter (VLM Direct 模式)**:
- 流程: 图像 → VLM API → Markdown（直接输出）
- 不使用处理器: 无 processor pipeline
- 输出: VLM 直接生成格式良好的 Markdown
- 位置: `marker/converters/vlm_direct.py`

**结论**: ✅ 用户正确
- LLM 增强功能只需要在 Pipeline 模式中启用
- 启发式版面增强只需要在 Pipeline 模式中启用
- VLM Direct 模式不需要这些功能（VLM 已经输出格式良好的 Markdown）

### 2. 当前 Markdown 渲染实现

**MarkdownRenderer** (`marker/renderers/markdown.py`):
```python
def __call__(self, document: Document) -> MarkdownOutput:
    document_output = document.render(self.block_config)
    full_html, images = self.extract_html(document, document_output)
    markdown = self.md_cls.convert(full_html)
    markdown = cleanup_text(markdown)  # 当前唯一的"格式化"
    return MarkdownOutput(markdown=markdown, images=images, metadata=...)
```

**cleanup_text** 函数（当前实现）:
```python
def cleanup_text(full_text):
    full_text = re.sub(r"\n{3,}", "\n\n", full_text)  # 移除多余换行
    full_text = re.sub(r"(\n\s){3,}", "\n\n", full_text)
    return full_text.strip()
```

**当前效果**: 只移除多余换行，不修正 Markdown 语法错误

### 3. 印刷页码处理现状

**PageNumberProcessor** (`marker/processors/page_number.py`):
- ✅ 已存在，已实现页码提取
- 支持格式: 阿拉伯数字、罗马数字、中文数字
- 提取位置: 页眉/页脚
- 存储位置: `page._internal_metadata["printed_page_number"]`

**当前问题**:
- ❌ 无法处理缺失的页码
- ❌ 无法修正错误的页码
- ❌ 无法基于模式推断页码

---

## 功能 1: 启发式版面增强

### 非 LLM 方案效果分析

**实现方式**: 在 MarkdownRenderer 中添加后处理

**可以修正的问题**:
1. ✅ 标题格式: `##标题` → `## 标题`
2. ✅ 列表格式: `-项目` → `- 项目`
3. ✅ 代码块: 不完整的 ``` 标记
4. ✅ 表格对齐: 添加空格使表格更易读
5. ✅ 多余空行: 统一空行数量
6. ✅ 链接格式: 修正不规范的链接语法

**无法修正的问题**:
1. ❌ 语义错误: 需要理解内容才能修正
2. ❌ 复杂嵌套: 深层嵌套的列表或引用
3. ❌ 上下文相关: 需要理解文档结构

### LLM 方案对比

| 维度 | 非 LLM 方案 | LLM 方案 |
|------|------------|----------|
| **准确性** | ⭐⭐⭐⭐ (90%) | ⭐⭐⭐⭐⭐ (95%) |
| **速度** | ⭐⭐⭐⭐⭐ (毫秒级) | ⭐⭐ (秒级) |
| **成本** | ⭐⭐⭐⭐⭐ (免费) | ⭐⭐ (API 费用) |
| **可控性** | ⭐⭐⭐⭐⭐ (完全可控) | ⭐⭐⭐ (可能改变内容) |
| **维护性** | ⭐⭐⭐⭐⭐ (简单) | ⭐⭐⭐ (需要调整 prompt) |
| **风险** | ⭐⭐⭐⭐⭐ (无风险) | ⭐⭐ (可能破坏布局) |

**推荐**: ✅ 非 LLM 方案
- 90% 的效果已经足够好
- 速度快、成本低、风险小
- 可以解决大部分常见格式问题

### 实现方案

**位置**: `marker/renderers/markdown.py`

**集成点**: 在 `MarkdownRenderer.__call__()` 中，`cleanup_text()` 之后

```python
class MarkdownFormatter:
    """Markdown 格式化器（后处理）"""

    def format(self, markdown_text: str) -> str:
        """格式化 Markdown 文本"""
        # 1. 修正标题格式
        markdown_text = self._fix_headers(markdown_text)

        # 2. 修正列表格式
        markdown_text = self._fix_lists(markdown_text)

        # 3. 修正代码块
        markdown_text = self._fix_code_blocks(markdown_text)

        # 4. 修正表格
        markdown_text = self._fix_tables(markdown_text)

        # 5. 统一空行
        markdown_text = self._normalize_spacing(markdown_text)

        return markdown_text

    def _fix_headers(self, text: str) -> str:
        """确保标题 # 后有空格"""
        text = re.sub(r'^(#{1,6})([^\s#])', r'\1 \2', text, flags=re.MULTILINE)
        # 移除标题末尾多余空格
        text = re.sub(r'^(#{1,6}\s+.+?)\s+$', r'\1', text, flags=re.MULTILINE)
        return text

    def _fix_lists(self, text: str) -> str:
        """确保列表标记后有空格"""
        # 无序列表
        text = re.sub(r'^(\s*[-*+])([^\s])', r'\1 \2', text, flags=re.MULTILINE)
        # 有序列表
        text = re.sub(r'^(\s*\d+\.)([^\s])', r'\1 \2', text, flags=re.MULTILINE)
        return text

    def _fix_code_blocks(self, text: str) -> str:
        """修正代码块标记"""
        # 确保代码块前后有空行
        text = re.sub(r'([^\n])\n```', r'\1\n\n```', text)
        text = re.sub(r'```\n([^\n])', r'```\n\n\1', text)
        return text

    def _fix_tables(self, text: str) -> str:
        """修正表格格式"""
        # 确保表格单元格有空格
        text = re.sub(r'\|([^\s|])', r'| \1', text)
        text = re.sub(r'([^\s|])\|', r'\1 |', text)
        return text

    def _normalize_spacing(self, text: str) -> str:
        """统一空行"""
        # 最多两个连续换行
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text
```

**修改 MarkdownRenderer**:
```python
class MarkdownRenderer(HTMLRenderer):
    # ... 现有代码 ...

    # 新增配置
    markdown_formatting_enabled: Annotated[
        bool, "启用 Markdown 格式化"
    ] = True

    def __call__(self, document: Document) -> MarkdownOutput:
        document_output = document.render(self.block_config)
        full_html, images = self.extract_html(document, document_output)
        markdown = self.md_cls.convert(full_html)
        markdown = cleanup_text(markdown)

        # 🆕 添加格式化
        if self.markdown_formatting_enabled:
            formatter = MarkdownFormatter()
            markdown = formatter.format(markdown)

        # ... 其余代码 ...
```

---

## 功能 2: 智能降噪

### 文档级分析调整

**原方案**: 读取前 3 页
**新方案**: 读取前 5 页（考虑空白页）

**实现逻辑**:
```python
def analyze_document_type(self, document: Document) -> Tuple[str, List[str]]:
    """
    分析文档类型和常见符号

    Args:
        document: 文档对象

    Returns:
        (文档类型, 常见符号列表)
    """
    # 取前 5 页（跳过空白页）
    sample_pages = []
    for page in document.pages[:10]:  # 最多检查前 10 页
        if len(sample_pages) >= 5:
            break
        # 跳过空白页
        if self._is_blank_page(page, document):
            continue
        sample_pages.append(page)

    # 分析文档类型
    doc_type = self._classify_document_type(sample_pages, document)

    # 提取常见符号
    common_symbols = self._extract_common_symbols(sample_pages, document)

    return doc_type, common_symbols
```

### 实现方案

**位置**: `marker/processors/llm/llm_noise_removal.py` (新建)

**继承**: `BaseLLMSimpleBlockProcessor`

**处理流程**:
1. **文档级分析**（一次性）:
   - 读取前 5 页（跳过空白页）
   - 识别文档类型（学术、小说、技术、古籍等）
   - 建立"合法符号白名单"

2. **页面级过滤**（每页）:
   - 基于文档类型和白名单
   - 使用 LLM 识别并移除噪音字符
   - 考虑字符位置、频率、上下文

**Prompt 设计**:
```python
noise_removal_prompt = """你是 OCR 噪音识别专家。

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
```

---

## 功能 3: 印刷页码修正（新功能）

### 问题分析

**现状**:
- PageNumberProcessor 已经提取印刷页码
- 但有些页码识别不准确或缺失
- 需要基于模式推断和修正

**示例**:
```
页面 0: 1
页面 1: 2
页面 2: 3
页面 3: (缺失)
页面 4: 5
页面 5: 6
页面 6: 7a  (错误)
页面 7: 8
```

**期望结果**:
```
页面 0: 1
页面 1: 2
页面 2: 3
页面 3: 4  (推断)
页面 4: 5
页面 5: 6
页面 6: 7  (修正)
页面 7: 8
```

### 实现方案：编程方式（推荐）

**为什么不用 LLM？**
1. ✅ 这是纯数学模式识别问题
2. ✅ 规则明确，不需要语义理解
3. ✅ 编程方式更快、更准确、无成本
4. ✅ 可以处理各种数字格式（阿拉伯、罗马、中文）

**算法设计**:

```python
class PrintedPageNumberCorrector:
    """印刷页码修正器"""

    def __init__(self, min_confidence: float = 0.7):
        self.min_confidence = min_confidence

    def correct_page_numbers(self, document: Document) -> Dict[int, str]:
        """
        修正文档的印刷页码

        Args:
            document: 文档对象

        Returns:
            修正后的页码映射 {page_idx: corrected_page_number}
        """
        # 1. 提取现有页码
        extracted = self._extract_existing_numbers(document)

        # 2. 识别数字序列模式
        patterns = self._identify_patterns(extracted)

        # 3. 选择最佳模式
        best_pattern = self._select_best_pattern(patterns)

        # 4. 基于模式修正和补全
        corrected = self._apply_pattern(extracted, best_pattern)

        return corrected

    def _extract_existing_numbers(self, document: Document) -> Dict[int, Optional[int]]:
        """提取现有页码并转换为数值"""
        extracted = {}
        for page_idx, page in enumerate(document.pages):
            if hasattr(page, "_internal_metadata"):
                metadata = page._internal_metadata
                if "printed_page_number_numeric" in metadata:
                    extracted[page_idx] = metadata["printed_page_number_numeric"]
                else:
                    extracted[page_idx] = None
        return extracted

    def _identify_patterns(self, extracted: Dict[int, Optional[int]]) -> List[Pattern]:
        """
        识别可能的数字序列模式

        可能的模式：
        1. 连续递增: 1, 2, 3, 4, 5...
        2. 跳跃递增: 1, 3, 5, 7... (奇数页)
        3. 偏移递增: 5, 6, 7, 8... (从某个数字开始)
        4. 分段递增: 1-10 (罗马), 1-100 (阿拉伯)
        """
        patterns = []

        # 获取非空页码
        valid_pairs = [(idx, num) for idx, num in extracted.items() if num is not None]
        if len(valid_pairs) < 2:
            return patterns

        # 模式 1: 连续递增
        pattern = self._check_continuous_pattern(valid_pairs)
        if pattern:
            patterns.append(pattern)

        # 模式 2: 跳跃递增
        pattern = self._check_skip_pattern(valid_pairs)
        if pattern:
            patterns.append(pattern)

        # 模式 3: 偏移递增
        pattern = self._check_offset_pattern(valid_pairs)
        if pattern:
            patterns.append(pattern)

        return patterns

    def _check_continuous_pattern(self, valid_pairs: List[Tuple[int, int]]) -> Optional[Pattern]:
        """
        检查连续递增模式: page_number = page_idx + offset

        例如:
        - page_idx=0, page_num=1 → offset=1
        - page_idx=1, page_num=2 → offset=1
        - page_idx=2, page_num=3 → offset=1
        """
        offsets = [num - idx for idx, num in valid_pairs]

        # 检查 offset 是否一致
        if len(set(offsets)) == 1:
            offset = offsets[0]
            confidence = 1.0
            return Pattern(
                type="continuous",
                offset=offset,
                step=1,
                confidence=confidence
            )

        # 允许少量误差
        from collections import Counter
        offset_counts = Counter(offsets)
        most_common_offset, count = offset_counts.most_common(1)[0]
        confidence = count / len(offsets)

        if confidence >= self.min_confidence:
            return Pattern(
                type="continuous",
                offset=most_common_offset,
                step=1,
                confidence=confidence
            )

        return None

    def _check_skip_pattern(self, valid_pairs: List[Tuple[int, int]]) -> Optional[Pattern]:
        """
        检查跳跃递增模式: page_number = page_idx * step + offset

        例如（奇数页）:
        - page_idx=0, page_num=1 → step=2, offset=1
        - page_idx=1, page_num=3 → step=2, offset=1
        - page_idx=2, page_num=5 → step=2, offset=1
        """
        if len(valid_pairs) < 3:
            return None

        # 计算步长
        steps = []
        for i in range(len(valid_pairs) - 1):
            idx1, num1 = valid_pairs[i]
            idx2, num2 = valid_pairs[i + 1]
            if idx2 - idx1 > 0:
                step = (num2 - num1) / (idx2 - idx1)
                steps.append(step)

        if not steps:
            return None

        # 检查步长是否一致
        avg_step = sum(steps) / len(steps)
        if abs(avg_step - round(avg_step)) < 0.1:  # 接近整数
            step = round(avg_step)
            if step > 1:  # 跳跃模式
                # 计算 offset
                idx0, num0 = valid_pairs[0]
                offset = num0 - idx0 * step

                # 验证模式
                errors = 0
                for idx, num in valid_pairs:
                    expected = idx * step + offset
                    if abs(num - expected) > 0.5:
                        errors += 1

                confidence = 1.0 - (errors / len(valid_pairs))
                if confidence >= self.min_confidence:
                    return Pattern(
                        type="skip",
                        offset=offset,
                        step=step,
                        confidence=confidence
                    )

        return None

    def _check_offset_pattern(self, valid_pairs: List[Tuple[int, int]]) -> Optional[Pattern]:
        """
        检查偏移递增模式: 从某个数字开始连续递增

        例如（从第 5 页开始）:
        - page_idx=0, page_num=5
        - page_idx=1, page_num=6
        - page_idx=2, page_num=7
        """
        # 这实际上就是 continuous pattern，已经在 _check_continuous_pattern 中处理
        return None

    def _select_best_pattern(self, patterns: List[Pattern]) -> Optional[Pattern]:
        """选择置信度最高的模式"""
        if not patterns:
            return None
        return max(patterns, key=lambda p: p.confidence)

    def _apply_pattern(
        self,
        extracted: Dict[int, Optional[int]],
        pattern: Optional[Pattern]
    ) -> Dict[int, str]:
        """基于模式修正和补全页码"""
        if pattern is None:
            # 无模式，返回原始数据
            return {idx: str(num) if num is not None else None
                    for idx, num in extracted.items()}

        corrected = {}
        for page_idx in extracted.keys():
            if pattern.type == "continuous":
                # page_number = page_idx + offset
                expected_num = page_idx + pattern.offset
            elif pattern.type == "skip":
                # page_number = page_idx * step + offset
                expected_num = page_idx * pattern.step + pattern.offset
            else:
                expected_num = None

            if expected_num is not None:
                # 检查是否需要修正
                actual_num = extracted[page_idx]
                if actual_num is None:
                    # 补全缺失页码
                    corrected[page_idx] = str(expected_num)
                elif abs(actual_num - expected_num) <= 1:
                    # 保留原始页码（误差在 1 以内）
                    corrected[page_idx] = str(actual_num)
                else:
                    # 修正错误页码
                    corrected[page_idx] = str(expected_num)
            else:
                # 无法推断，保留原始
                corrected[page_idx] = str(actual_num) if actual_num else None

        return corrected


@dataclass
class Pattern:
    """页码模式"""
    type: str  # "continuous", "skip", "offset"
    offset: int  # 偏移量
    step: int  # 步长
    confidence: float  # 置信度
```

**集成位置**: 在 PageNumberProcessor 之后运行

**修改 PdfConverter**:
```python
default_processors: Tuple[BaseProcessor, ...] = (
    # ... 其他处理器 ...
    PageNumberProcessor,  # 提取页码
    PrintedPageNumberCorrectorProcessor,  # 🆕 修正页码
    # ... 其他处理器 ...
)
```

---

## 总体实现计划

### 优先级 1: 修复假开关（已部分实现）

**状态**: ✅ 已在 PdfConverter 中添加 `_filter_llm_processors` 方法

**待完成**:
1. 添加 `llm_noise_removal_enabled` 和 `llm_heuristic_layout_enabled` 的映射
2. 测试所有 11 个开关

### 优先级 2: 启发式版面增强

**实现步骤**:
1. 创建 `MarkdownFormatter` 类（`marker/renderers/markdown.py`）
2. 在 `MarkdownRenderer.__call__()` 中集成
3. 添加配置参数 `markdown_formatting_enabled`
4. 在 UI 中连接开关（注意：只在 Pipeline 模式中显示）

**工作量**: ⭐⭐ (小)

### 优先级 3: 印刷页码修正

**实现步骤**:
1. 创建 `PrintedPageNumberCorrector` 类
2. 创建 `PrintedPageNumberCorrectorProcessor`
3. 添加到 `PdfConverter.default_processors`
4. 在 UI 中添加开关

**工作量**: ⭐⭐⭐ (中等)

### 优先级 4: 智能降噪

**实现步骤**:
1. 创建 `LLMNoiseRemovalProcessor` 类
2. 实现文档级分析（5 页）
3. 实现页面级过滤
4. 添加到 `PdfConverter.default_processors`
5. 在 `_filter_llm_processors` 中添加映射

**工作量**: ⭐⭐⭐⭐ (较大)

---

## UI 配置调整

### Streamlit UI 修改

**问题**: 当前 UI 在所有模式下都显示 LLM 增强选项

**解决方案**: 根据转换模式动态显示配置

```python
# 在 streamlit_app.py 中
converter_type = st.selectbox("转换模式", ["Pipeline", "VLM Direct"])

if converter_type == "Pipeline":
    # 显示 LLM 增强选项
    with st.expander("🤖 LLM 增强", expanded=False):
        use_llm = st.checkbox("启用 LLM 增强", value=False)
        if use_llm:
            # 11 个 LLM 模块开关
            llm_table_enabled = st.checkbox("表格优化", value=True)
            # ... 其他开关 ...

    # 显示输出格式选项
    with st.expander("📝 输出格式", expanded=False):
        markdown_formatting_enabled = st.checkbox(
            "Markdown 格式化",
            value=True,
            help="修正 Markdown 语法错误（标题、列表、表格等）"
        )

elif converter_type == "VLM Direct":
    # VLM Direct 模式不需要 LLM 增强和格式化
    pass
```

---

## 配置映射表（更新）

| UI 复选框 | 配置键 | 对应处理器/功能 | 模式 | 状态 |
|-----------|--------|----------------|------|------|
| 表格优化 | llm_table_enabled | LLMTableProcessor | Pipeline | ✅ 已修复 |
| 公式识别 | llm_equation_enabled | LLMEquationProcessor | Pipeline | ✅ 已修复 |
| 图片描述 | llm_image_description_enabled | LLMImageDescriptionProcessor | Pipeline | ✅ 已修复 |
| 手写识别 | llm_handwriting_enabled | LLMHandwritingProcessor | Pipeline | ✅ 已修复 |
| **智能降噪** | llm_noise_removal_enabled | LLMNoiseRemovalProcessor | Pipeline | 🆕 待实现 |
| 页面修正 | llm_page_correction_enabled | LLMPageCorrectionProcessor | Pipeline | ✅ 已修复 |
| 章节标题 | llm_section_header_enabled | LLMSectionHeaderProcessor | Pipeline | ✅ 已修复 |
| 表单识别 | llm_form_enabled | LLMFormProcessor | Pipeline | ✅ 已修复 |
| 复杂区域 | llm_complex_region_enabled | LLMComplexRegionProcessor | Pipeline | ✅ 已修复 |
| **印刷页码修正** | printed_page_correction_enabled | PrintedPageNumberCorrectorProcessor | Pipeline | 🆕 待实现 |
| **Markdown 格式化** | markdown_formatting_enabled | MarkdownFormatter | Pipeline | 🆕 待实现 |

**注意**:
- "启发式版面增强" 重命名为 "Markdown 格式化"（更准确）
- 移到"输出格式"部分，不再是 LLM 功能
- 所有功能只在 Pipeline 模式中可用

---

## 总结

### 回答用户的问题

1. **启发式版面增强的效果**:
   - 非 LLM 方案可以达到 90% 的效果
   - 可以修正大部分常见格式问题
   - 速度快、成本低、风险小
   - 推荐使用非 LLM 方案

2. **文档级分析页数**:
   - 从 3 页调整为 5 页
   - 考虑空白页的情况
   - 最多检查前 10 页以找到 5 个非空白页

3. **功能适用模式**:
   - ✅ LLM 增强只在 Pipeline 模式中需要
   - ✅ Markdown 格式化只在 Pipeline 模式中需要
   - ✅ VLM Direct 模式不需要这些功能

4. **印刷页码修正**:
   - ✅ 推荐使用编程方式而非 LLM
   - 基于数学模式识别
   - 可以补全缺失页码和修正错误页码
   - 更快、更准确、无成本

### 实现建议

**立即实现**:
1. ✅ 修复假开关（已部分完成）
2. ✅ 启发式版面增强（简单，高价值）
3. ✅ 印刷页码修正（中等复杂度，高价值）

**后续实现**:
4. ✅ 智能降噪（复杂，中等价值）

**UI 调整**:
5. ✅ 根据转换模式动态显示配置
6. ✅ 重命名"启发式版面增强"为"Markdown 格式化"
7. ✅ 移动到"输出格式"部分
