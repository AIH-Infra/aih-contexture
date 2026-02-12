# LLM 新功能整体分析报告

## 概述

本报告分析两个提议的 LLM 功能模块：
1. **智能降噪 (Smart Denoising)** - 过滤 OCR 产生的无意义特殊字符
2. **启发式版面增强 (Heuristic Layout Enhancement)** - 完善 Markdown 格式化

## 当前状态

### 现有相关功能

1. **IgnoreTextProcessor** (marker/processors/ignoretext.py)
   - 功能：识别并忽略重复文本块（页眉、页脚、页码）
   - 方法：基于文本出现频率和连续性
   - 局限：只处理重复文本块，不处理 OCR 噪音字符

2. **cleanup_text** (marker/renderers/markdown.py)
   - 功能：清理多余换行符
   - 方法：正则表达式替换
   - 局限：只处理格式问题，不处理内容噪音

3. **现有 LLM 处理器**
   - LLMTableProcessor: 修正表格结构
   - LLMEquationProcessor: 识别公式
   - LLMPageCorrectionProcessor: 修正页面布局
   - 等等...

### UI 配置状态

在 streamlit_app.py 中已有两个复选框：
- `llm_noise_removal_enabled` - 智能降噪
- `llm_heuristic_layout_enabled` - 启发式版面增强

但对应的处理器**不存在**，这两个是"假开关"。

---

## 功能 1: 智能降噪 (Smart Denoising)

### 问题定义

**OCR 噪音的类型**：
1. **随机特殊字符**: `~`, `^`, `*`, `#`, `@`, `%` 等无意义符号
2. **错误识别的符号**: 将图像瑕疵、污点识别为字符
3. **重复字符**: `....`, `----`, `====` 等
4. **乱码字符**: Unicode 控制字符、零宽字符
5. **位置错误的字符**: 页边距外的孤立字符

**与 IgnoreTextProcessor 的区别**：
- IgnoreTextProcessor: 过滤**重复文本块**（整行/整段）
- 智能降噪: 过滤**字符级噪音**（单个或少量字符）

### 核心问题：需要多少上下文？

**选项 A: 单页上下文**
- 优点：
  - 处理速度快
  - API 调用成本低
  - 实现简单
- 缺点：
  - 无法理解文档整体类型
  - 可能误判某些特殊符号（如数学符号）
  - 对跨页内容判断不准确

**选项 B: 多页上下文**
- 优点：
  - 可以理解文档类型（学术论文、小说、技术文档等）
  - 更准确判断符号是否有意义
  - 可以识别文档特定的符号使用模式
- 缺点：
  - 处理速度慢
  - API 调用成本高（需要传输多页图像或文本）
  - 实现复杂

**推荐方案: 混合方法**
1. **文档级分析（一次性）**：
   - 读取前 3-5 页
   - 识别文档类型（学术、小说、技术、古籍等）
   - 建立"合法符号白名单"

2. **页面级过滤（每页）**：
   - 基于文档类型和白名单
   - 识别并移除噪音字符
   - 考虑字符位置、频率、上下文

### 实现方案

#### 方案 A: 简单启发式（不使用 LLM）

```python
class NoiseRemovalProcessor(BaseProcessor):
    """
    基于启发式规则的噪音过滤器
    """
    # 常见 OCR 噪音模式
    noise_patterns = [
        r'[~^*#@%]{2,}',  # 重复特殊符号
        r'\.{4,}',         # 过多句点
        r'-{4,}',          # 过多破折号
        r'_{4,}',          # 过多下划线
    ]

    # 孤立字符阈值
    isolated_char_distance = 50  # 像素

    def __call__(self, document: Document):
        for page in document.pages:
            for block in page.contained_blocks(document, self.block_types):
                # 检查每个文本块
                cleaned_text = self.remove_noise(block.raw_text(document))
                # 更新块内容
                ...
```

**优点**：
- 实现简单
- 无 API 成本
- 处理速度快

**缺点**：
- 可能误判
- 无法理解语义
- 规则需要不断调整

#### 方案 B: LLM 辅助（推荐）

```python
class LLMNoiseRemovalProcessor(BaseLLMSimpleBlockProcessor):
    """
    使用 LLM 识别和移除 OCR 噪音
    """
    block_types = (BlockTypes.Text, BlockTypes.TextInlineMath)

    noise_removal_prompt = """你是一个 OCR 噪音识别专家。

文档类型：{document_type}
常见符号：{common_symbols}

请分析以下文本块，识别并移除 OCR 产生的噪音字符：

原文：
{text}

噪音字符通常包括：
1. 随机特殊符号（不符合文档类型）
2. 孤立的无意义字符
3. 明显的识别错误

请输出：
1. 清理后的文本
2. 移除的字符列表
3. 置信度（1-5）
"""

    def __call__(self, document: Document):
        # 第一步：文档级分析
        doc_type, common_symbols = self.analyze_document(document)

        # 第二步：页面级过滤
        for page in document.pages:
            for block in page.contained_blocks(document, self.block_types):
                prompt = self.noise_removal_prompt.format(
                    document_type=doc_type,
                    common_symbols=common_symbols,
                    text=block.raw_text(document)
                )
                response = self.llm_service(prompt, None, block, NoiseRemovalSchema)
                # 更新块内容
                ...
```

**优点**：
- 语义理解准确
- 可以适应不同文档类型
- 误判率低

**缺点**：
- API 成本较高
- 处理速度较慢
- 需要设计好的 prompt

### 可行性评估

| 维度 | 评分 | 说明 |
|------|------|------|
| **技术可行性** | ⭐⭐⭐⭐⭐ | 完全可行，有清晰的实现路径 |
| **实现复杂度** | ⭐⭐⭐ | 中等复杂度，需要设计好的 prompt 和逻辑 |
| **效果预期** | ⭐⭐⭐⭐ | 预期效果良好，可以显著减少噪音 |
| **成本** | ⭐⭐⭐ | LLM 方案有 API 成本，启发式方案无成本 |
| **维护性** | ⭐⭐⭐⭐ | 代码结构清晰，易于维护和调整 |

**总体评估**: ✅ **推荐实现**

---

## 功能 2: 启发式版面增强 (Heuristic Layout Enhancement)

### 问题定义

**目标**：完善 Markdown 格式化��不破坏原有版面识别结果

**具体需求**：
1. **格式化语法标识**: 确保 Markdown 语法正确
2. **不改变内容**: 不修改文本内容本身
3. **不破坏布局**: 保持原有的块结构和层次

**示例问题**：

```markdown
# 错误示例 1: 标题格式不一致
##标题1
## 标题2
###  标题3

# 正确格式
## 标题1
## 标题2
### 标题3

# 错误示例 2: 列表格式不规范
-项目1
- 项目2
  -子项目

# 正确格式
- 项目1
- 项目2
  - 子项目

# 错误示例 3: 代码块标记不完整
```
代码
``

# 正确格式
```
代码
```

# 错误示例 4: 表格对齐问题
|列1|列2|
|---|---|
|内容1|内容2|

# 正确格式
| 列1 | 列2 |
|-----|-----|
| 内容1 | 内容2 |
```

### 核心挑战

1. **如何识别格式问题？**
   - Markdown 语法错误
   - 不一致的格式风格
   - 缺失的空格或换行

2. **如何避免破坏布局？**
   - 不改变块的类型（Text → SectionHeader）
   - 不改变块的层次结构
   - 不改变块的顺序

3. **什么是"完美"的格式？**
   - 符合 CommonMark 规范
   - 一致的风格（空格、缩进）
   - 可读性强

### 实现方案

#### 方案 A: 后处理（在渲染阶段）

```python
class MarkdownFormatter:
    """
    在 Markdown 渲染后进行格式化
    """
    def format_markdown(self, markdown_text: str) -> str:
        # 1. 修正标题格式
        markdown_text = self.fix_headers(markdown_text)

        # 2. 修正列表格式
        markdown_text = self.fix_lists(markdown_text)

        # 3. 修正代码块
        markdown_text = self.fix_code_blocks(markdown_text)

        # 4. 修正表格
        markdown_text = self.fix_tables(markdown_text)

        # 5. 统一空行
        markdown_text = self.normalize_spacing(markdown_text)

        return markdown_text

    def fix_headers(self, text: str) -> str:
        # 确保 # 后有空格
        text = re.sub(r'^(#{1,6})([^\s#])', r'\1 \2', text, flags=re.MULTILINE)
        return text

    def fix_lists(self, text: str) -> str:
        # 确保列表标记后有空格
        text = re.sub(r'^(\s*[-*+])([^\s])', r'\1 \2', text, flags=re.MULTILINE)
        return text

    # ... 其他方法
```

**集成点**: 在 MarkdownRenderer.generate_markdown() 的最后阶段

**优点**：
- 实现简单
- 不影响文档结构
- 无 API 成本
- 处理速度快

**缺点**：
- 只能处理格式问题，不能处理语义问题
- 可能无法处理复杂的格式错误

#### 方案 B: LLM 辅助（不推荐）

```python
class LLMHeuristicLayoutProcessor(BaseLLMProcessor):
    """
    使用 LLM 完善 Markdown 格式
    """
    heuristic_layout_prompt = """你是一个 Markdown 格式化专家。

请修正以下 Markdown 文本的格式问题，但不要改变内容和结构：

原文：
{markdown_text}

要求：
1. 修正语法错误（标题、列表、代码块等）
2. 统一格式风格（空格、缩进）
3. 不改变文本内容
4. 不改变块的顺序和层次

请输出修正后的 Markdown 文本。
"""
```

**优点**：
- 可以处理复杂的格式问题
- 可以理解语义

**缺点**：
- API 成本高
- 处理速度慢
- 可能改变内容（LLM 不可控）
- **风险高**：可能破坏原有布局

### 推荐方案：方案 A（后处理）

**理由**：
1. **简单有效**: 启发式规则可以解决大部分格式问题
2. **无成本**: 不需要 API 调用
3. **可控**: 不会意外改变内容
4. **快速**: 正则表达式处理速度快

**实现位置**：
- 在 `MarkdownRenderer` 中添加 `MarkdownFormatter`
- 在 `generate_markdown()` 的最后调用

### 可行性评估

| 维度 | 评分 | 说明 |
|------|------|------|
| **技术可行性** | ⭐⭐⭐⭐⭐ | 完全可行，有成熟的实现方案 |
| **实现复杂度** | ⭐⭐ | 简单，主要是正则表达式 |
| **效果预期** | ⭐⭐⭐⭐ | 可以解决大部分格式问题 |
| **成本** | ⭐⭐⭐⭐⭐ | 无成本（不使用 LLM） |
| **维护性** | ⭐⭐⭐⭐⭐ | 代码简单，易于维护 |

**总体评估**: ✅ **强烈推荐实现**（使用方案 A）

---

## 总体建议

### 1. 智能降噪 (Smart Denoising)

**推荐实现方案**: LLM 辅助 + 启发式规则混合

**实现步骤**：
1. 创建 `LLMNoiseRemovalProcessor` 继承 `BaseLLMSimpleBlockProcessor`
2. 实现文档级分析（识别文档类型）
3. 实现页面级过滤（移除噪音字符）
4. 添加启发式规则作为快速预过滤
5. 在 UI 中连接 `llm_noise_removal_enabled` 开关

**预期效果**: ⭐⭐⭐⭐ (良好)

**实现难度**: ⭐⭐⭐ (中等)

### 2. 启发式版面增强 (Heuristic Layout Enhancement)

**推荐实现方案**: 后处理格式化（不使用 LLM）

**实现步骤**：
1. 创建 `MarkdownFormatter` 类
2. 实现各种格式修正方法（标题、列表、代码块、表格）
3. 在 `MarkdownRenderer.generate_markdown()` 中集成
4. 在 UI 中连接 `llm_heuristic_layout_enabled` 开关

**预期效果**: ⭐⭐⭐⭐ (良好)

**实现难度**: ⭐⭐ (简单)

**注意**: 这个功能**不应该**是 LLM 处理器，而应该是渲染器的后处理步骤。建议重命名为 `markdown_formatting_enabled` 更准确。

### 3. 修复假开关问题

**必须同时修复**: 让所有 11 个 LLM 模块开关真正控制处理器执行

**实现步骤**：
1. 在 `PdfConverter.__init__()` 中添加处理器过滤逻辑
2. 根据配置标志过滤处理器列表
3. 测试每个开关是否正确控制对应处理器

---

## 实现优先级

### 优先级 1: 修复假开关 ⚠️
- **重要性**: 🔴 严重
- **影响**: 用户以为关闭了功能，但实际还在运行，浪费 API 调用
- **工作量**: 中等
- **建议**: 立即修复

### 优先级 2: 启发式版面增强 ✅
- **重要性**: 🟢 中等
- **影响**: 提升 Markdown 输出质量
- **工作量**: 小
- **建议**: 优先实现（简单且有效）

### 优先级 3: 智能降噪 ✅
- **重要性**: 🟡 中等
- **影响**: 减少 OCR 噪音，提升内容质量
- **工作量**: 中等
- **建议**: 在修复假开关后实现

---

## 结论

### 两个功能是否可以"很有效很简单"地实现？

**智能降噪**: ✅ 可以有效实现，但不算"很简单"
- 需要设计好的 LLM prompt
- 需要文档级和页面级两层处理
- 预期效果良好

**启发式版面增强**: ✅ 可以很有效很简单地实现
- 使用正则表达式后处理
- 不需要 LLM（建议不使用）
- 实现简单，效果好

### 最终建议

1. ✅ **立即修复假开关问题** - 这是严重的 bug
2. ✅ **实现启发式版面增强** - 简单有效，使用后处理方案
3. ✅ **实现智能降噪** - 有价值，使用 LLM 辅助方案
4. ⚠️ **重新考虑命名** - "启发式版面增强"不应该是 LLM 功能，建议移到"输出格式"部分

---

## 附录：配置映射表

| UI 复选框 | 配置键 | 对应处理器 | 状态 |
|-----------|--------|-----------|------|
| 表格优化 | llm_table_enabled | LLMTableProcessor | ❌ 假开关 |
| 公式识别 | llm_equation_enabled | LLMEquationProcessor | ❌ 假开关 |
| 图片描述 | llm_image_description_enabled | LLMImageDescriptionProcessor | ❌ 假开关 |
| 手写识别 | llm_handwriting_enabled | LLMHandwritingProcessor | ❌ 假开关 |
| **智能降噪** | llm_noise_removal_enabled | **不存在** | ❌ 假开关 |
| 页面修正 | llm_page_correction_enabled | LLMPageCorrectionProcessor | ❌ 假开关 |
| 章节标题 | llm_section_header_enabled | LLMSectionHeaderProcessor | ❌ 假开关 |
| 表单识别 | llm_form_enabled | LLMFormProcessor | ❌ 假开关 |
| 复杂区域 | llm_complex_region_enabled | LLMComplexRegionProcessor | ❌ 假开关 |
| 印刷页面修正 | llm_printed_page_correction_enabled | **不存在** | ❌ 假开关 |
| **启发式版面增强** | llm_heuristic_layout_enabled | **不存在** | ❌ 假开关 |

**注意**:
- "智能降噪"和"启发式版面增强"对应的处理器不存在，需要新建
- 其他 9 个处理器存在，但开关不起作用，需要修复
