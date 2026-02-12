# Surya 与 VLM 版面识别对齐方案

## 问题分析

VLM 版面识别虽然能力强，但识别结果与 Surya 的原生行为不一致，导致后续处理出现问题。

### 核心问题
1. **标签不一致**: VLM 可能返回 Surya 不使用的标签
2. **块类型混淆**: 特别是 Footnote, PageFooter, Text 的区分
3. **坐标精度**: VLM 的坐标可能不够精确
4. **阅读顺序**: position 字段的排序逻辑不一致

## Surya 的原生行为

### 1. 支持的块类型

根据 `marker/schema/__init__.py` 和 `marker/services/layout_base.py`:

```python
SUPPORTED_LAYOUT_LABELS = [
    "Text",              # 普通文本
    "Caption",           # 图表标题
    "Code",              # 代码块
    "Figure",            # 图形
    "Footnote",          # 脚注
    "Form",              # 表单
    "Equation",          # 公式
    "Handwriting",       # 手写
    "TextInlineMath",    # 内联数学
    "ListItem",          # 列表项
    "PageFooter",        # 页脚
    "PageHeader",        # 页眉
    "Picture",           # 图片
    "SectionHeader",     # 章节标题
    "Table",             # 表格
    "TableOfContents",   # 目录
    "ComplexRegion",     # 复杂区域
]
```

### 2. 标签规范化规则

`BaseLayoutService.normalize_label()` 提供了标签映射：

```python
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
```

### 3. 数据结构

```python
LayoutBox(
    label="Text",                    # 必须是 SUPPORTED_LAYOUT_LABELS 之一
    position=0,                      # 阅读顺序（0开始）
    top_k={"Text": 0.95},           # 置信度字典
    polygon=[[x1,y1], [x2,y2], [x3,y3], [x4,y4]]  # 四角坐标
)
```

### 4. Surya 的块类型使用习惯

基于 Surya 的训练数据和实际行为：

#### Footnote (脚注)
- **位置**: 页面底部
- **特征**: 字号小，有编号标记
- **Surya 行为**: 通常能识别明显的脚注区域

#### PageFooter (页脚)
- **位置**: 页面最底部边缘
- **内容**: 页码、版权信息（简短）
- **Surya 行为**: 识别页面边缘的元信息

#### PageHeader (页眉)
- **位置**: 页面最顶部边缘
- **内容**: 章节标题、书名、页码
- **Surya 行为**: 识别页面顶部的元信息

#### Text (正文)
- **位置**: 页面主体
- **特征**: 标准字号，段落形式
- **Surya 行为**: 主要内容区域

#### SectionHeader (章节标题)
- **特征**: 字号大，加粗
- **Surya 行为**: 识别明显的标题

## VLM 对齐策略

### 1. 严格使用 Surya 的标签集

**问题**: VLM 可能返回不在 SUPPORTED_LAYOUT_LABELS 中的标签

**解决**: 在提示词中明确限制标签范围

```
label: Must be EXACTLY one of: Text, Caption, Code, Figure, Footnote, Form,
Equation, Handwriting, TextInlineMath, ListItem, PageFooter, PageHeader,
Picture, SectionHeader, Table, TableOfContents, ComplexRegion

IMPORTANT: Use these exact label names. Do not use variations or synonyms.
```

### 2. 对齐块类型定义

#### Footnote vs PageFooter - 关键区分

**Surya 的行为**:
- **Footnote**: 页面底部的注释内容，有编号，字号小
- **PageFooter**: 页面最底部边缘的页码/元信息

**VLM 对齐规则**:
```
Footnote:
- Location: Bottom 10-25% of page (ABOVE PageFooter if present)
- Content: Annotation text with numbered markers (<sup>1</sup>, [1], etc.)
- Font size: 60-80% of main text
- Has separation line or whitespace from main text

PageFooter:
- Location: Bottom 0-5% of page (absolute bottom margin)
- Content: Page numbers, copyright, brief metadata
- Font size: Small
- Usually centered or at corners
- NO numbered markers

CRITICAL: If a region has numbered markers (<sup>1</sup>, [1]), it is Footnote, NOT PageFooter.
If it's just a page number without annotation content, it's PageFooter.
```

#### Text vs Footnote - 关键区分

**Surya 的行为**:
- **Text**: 主体内容，标准字号
- **Footnote**: 底部注释，字号明显更小

**VLM 对齐规则**:
```
Text:
- Location: Main body area (middle 60-80% of page)
- Font size: Standard (baseline)
- No numbered markers at start

Footnote:
- Location: Bottom area (below main text)
- Font size: Noticeably smaller (60-80% of Text)
- Has numbered markers
- Separated from Text by line or space

CRITICAL: Size difference is key. If text is significantly smaller AND at bottom,
it's likely Footnote, not Text.
```

### 3. 阅读顺序对齐

**Surya 的行为**: 按照从上到下、从左到右的阅读顺序分配 position

**VLM 对齐规则**:
```
Order regions by reading order:
1. PageHeader (if present)
2. Main content (top to bottom, left to right)
3. Footnote (if present)
4. PageFooter (if present)

For multi-column layouts:
- Process left column first, then right column
- Within each column: top to bottom

Assign position values starting from 0, incrementing by 1.
```

### 4. 坐标精度对齐

**Surya 的行为**: 提供紧贴内容的精确边界框

**VLM 对齐规则**:
```
Bounding boxes must:
- Tightly fit the content (no excessive padding)
- Include all text/content within the region
- Not overlap with other regions (unless necessary)
- Use pixel coordinates relative to image size

For Footnote:
- Include the marker AND the annotation text
- Include all lines of the footnote
- Stop at the separation line (don't include the line itself)
```

### 5. 置信度对齐

**Surya 的行为**: 提供 top_k 字典，包含多个候选标签的置信度

**VLM 对齐规则**:
```
Provide confidence scores in top_k:
- Primary label: 0.7-1.0 (high confidence)
- Alternative labels: 0.1-0.3 (if applicable)

Example:
{
  "label": "Footnote",
  "top_k": {"Footnote": 0.95, "Text": 0.03, "PageFooter": 0.02},
  ...
}

If uncertain between Footnote and Text:
- Check size: smaller = Footnote
- Check location: bottom = Footnote
- Check markers: has markers = Footnote
```

## 更新后的 VLM 提示词模板

### 核心改进

1. **明确标签集**: 只使用 SUPPORTED_LAYOUT_LABELS
2. **详细区分规则**: 特别是 Footnote vs PageFooter vs Text
3. **Surya 行为参考**: 说明 Surya 如何处理这些块类型
4. **量化标准**: 提供具体的位置、大小百分比

### 示例：对齐后的 Footnote 定义

```
### Footnote (脚注) - CRITICAL DISTINCTION

**Definition** (aligned with Surya):
Footnote is annotation text at the bottom of the page with numbered markers.

**Visual Characteristics**:
- Location: Bottom 10-25% of page (ABOVE PageFooter if present)
- Font size: 60-80% of main Text size (significantly smaller)
- Markers: MUST have numbered markers (<sup>1</sup>, <sup>2</sup>, [1], [2], ①, ②, *)
- Separation: Horizontal line or significant whitespace separating from main Text
- Content: Annotation or citation text (not just page numbers)

**Key Distinctions** (Surya behavior):
- vs Text: Footnote is smaller, at bottom, has markers
- vs PageFooter: Footnote has annotation content with markers; PageFooter is just page numbers
- vs Caption: Caption is near Figure/Table; Footnote is at page bottom

**Decision Rules**:
1. Has numbered markers? → Likely Footnote (not PageFooter)
2. Significantly smaller than main text? → Likely Footnote (not Text)
3. At bottom with separation line? → Likely Footnote
4. Just page numbers without annotation? → PageFooter (not Footnote)

**Surya Convention**:
Surya identifies Footnote as a distinct region at page bottom with smaller text and markers.
Follow this convention strictly.
```

## 实施步骤

### 第一步：更新提示词模板

1. 在所有模板中添加 "Surya Alignment" 部分
2. 明确标签集和使用规则
3. 添加详细的块类型区分规则
4. 提供量化标准（位置百分比、大小比例）

### 第二步：添加后处理验证

在 VlmLayoutService 中添加验证逻辑：

```python
def post_process_results(self, layout_result: LayoutResult) -> LayoutResult:
    """
    后处理 VLM 结果，确保与 Surya 行为一致
    """
    # 1. 验证标签
    layout_result = self.validate_labels(layout_result)

    # 2. 检查 Footnote vs PageFooter
    layout_result = self.validate_footnote_pagefooter(layout_result)

    # 3. 重新排序（确保阅读顺序正确）
    layout_result = self.reorder_by_position(layout_result)

    return layout_result
```

### 第三步：测试验证

使用相同文档分别���试 Surya 和 VLM，对比结果：

```python
# Surya 结果
surya_result = surya_layout_service.detect_layout([image])

# VLM 结果
vlm_result = vlm_layout_service.detect_layout([image])

# 对比
compare_layout_results(surya_result, vlm_result)
```

## 预期效果

### 对齐前
```
VLM 识别:
- Text (正文) ✓
- Text (脚注被误识别) ✗
- Footer (使用了错误的标签) ✗
```

### 对齐后
```
VLM 识别:
- Text (正文) ✓
- Footnote (正确识别) ✓
- PageFooter (使用正确标签) ✓
```

## 总结

通过严格对齐 Surya 的标签集、块类型定义、阅读顺序和坐标规范，VLM 的输出将与 Surya 保持一致，确保后续处理模块能够正确工作。

关键点：
1. ✅ 使用完全相同的标签集
2. ✅ 遵循 Surya 的块类型定义
3. ✅ 提供详细的区分规则
4. ✅ 添加后处理验证
5. ✅ 量化标准（位置、大小百分比）
