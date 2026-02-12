# Surya 对齐版 VLM 提示词使用指南

## 问题背景

VLM 版面识别虽然能力强（如 Qwen3-VL-Max），但识别结果与 Surya 的原生行为不一致，导致：
- 脚注识别混乱
- PageFooter 与 Footnote 混淆
- 块类型标签不规范
- 后续处理模块出错

## 解决方案：Surya 对齐版

创建了严格对齐 Surya 行为的提示词模板，确保：
1. ✅ 使用完全相同的标签集
2. ✅ 遵循 Surya 的块类型定义
3. ✅ 匹配 Surya 的识别习惯
4. ✅ 提供详细的区分规则

## 使用方法

### 配置示例

```python
config = {
    "layout_backend": "vlm",
    "vlm_layout_prompt_template": "surya_modern",  # Surya 对齐版
    "vlm_layout_model": "qwen-vl-max",
    "disable_ocr": True,
    "use_printed_page_number": True,
}

converter = PdfConverter(artifact_dict=model_dict, config=config)
result = converter("document.pdf")
```

### 可用模板

1. **surya_modern** - 现代出版物（Surya 对齐）
2. **surya_academic** - 学术论文（Surya 对齐）

## 核心改进

### 1. 严格的标签集

**Surya 支持的标签**（完全一致）:
```
Text, Caption, Code, Figure, Footnote, Form, Equation, Handwriting,
TextInlineMath, ListItem, PageFooter, PageHeader, Picture, SectionHeader,
Table, TableOfContents, ComplexRegion
```

**禁止使用的变体**:
- ❌ "Footer" → ✅ "PageFooter"
- ❌ "Header" → ✅ "PageHeader"
- ❌ "Image" → ✅ "Picture"
- ❌ "Paragraph" → ✅ "Text"

### 2. Footnote vs PageFooter - 关键区分

这是最容易混淆的两个类型，Surya 对齐版提供了明确的区分规则：

#### Footnote (脚注)
```
定义: 页面底部的注释内容，有编号标记

特征:
- 位置: 底部 10-25%（在 PageFooter 之上）
- 字号: 60-80% 正文大小
- 标记: 必须有 <sup>1</sup>, [1], ①, * 等编号
- 内容: 注释文本（可能多行）
- 分隔: 与正文有分隔线或空白

判断规则: 有编号标记 + 注释内容 = Footnote
```

#### PageFooter (页脚)
```
定义: 页面最底部边缘的页码和元信息

特征:
- 位置: 底部 0-5%（绝对底部边缘）
- 内容: 页码、版权信息（简短，1-2行）
- 无编号标记
- 通常居中或在角落

判断规则: 只有页码，无注释内容 = PageFooter
```

#### 决策树
```
底部区域的文本
├─ 有编号标记（<sup>1</sup>, [1]）？
│  ├─ 是 → Footnote
│  └─ 否 → 继续
├─ 有注释内容（多行）？
│  ├─ 是 → Footnote
│  └─ 否 → 继续
└─ 只有页码？
   └─ 是 → PageFooter
```

### 3. Footnote vs Text - 关键区分

#### Text (正文)
```
- 位置: 主体区域（中间 60-80%）
- 字号: 标准大小（基准）
- 无编号标记
```

#### Footnote (脚注)
```
- 位置: 底部区域
- 字号: 明显更小（60-80% 正文）
- 有编号标记
```

#### 判断规则
```
字号明显更小 + 底部位置 + 有标记 = Footnote
否则 = Text
```

### 4. 量化标准

Surya 对齐版提供了具体的量化标准：

**位置百分比**:
- PageHeader: 顶部 0-5%
- PageFooter: 底部 0-5%
- Footnote: 底部 10-25%
- Text: 中间 60-80%

**字号比例**（相对于 Text）:
- Footnote: 60-80%
- PageHeader/PageFooter: 70-90%
- SectionHeader: 120-150%
- Caption: 80-90%

### 5. 阅读顺序

Surya 的阅读顺序规则：
```
1. PageHeader（如果有）
2. 主体内容（从上到下）
   - 多栏布局：先左栏，再右栏
3. Footnote（如果有）
4. PageFooter（如果有）
```

## 对比：三个版本

### 基础版
```python
"vlm_layout_prompt_template": "modern"
```
- 简洁的提示词
- 只列出标签名称
- 适合快速识别
- ⚠️ 可能出现标签混淆

### 增强版
```python
"vlm_layout_prompt_template": "modern_enhanced"
```
- 详细的块类型规范
- 包含视觉特征描述
- 适合脚注密集文档
- ⚠️ 可能与 Surya 行为有差异

### Surya 对齐版（推荐）
```python
"vlm_layout_prompt_template": "surya_modern"
```
- 严格对齐 Surya 行为
- 使用 Surya 的标签集和定义
- 提供详细的区分规则
- ✅ 与后续处理模块完全兼容

## 测试对比

### 测试脚本

```python
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict

# 基础版
config_basic = {
    "layout_backend": "vlm",
    "vlm_layout_prompt_template": "modern",
}

# Surya 对齐版
config_aligned = {
    "layout_backend": "vlm",
    "vlm_layout_prompt_template": "surya_modern",
}

model_dict = create_model_dict()

# 测试
converter_basic = PdfConverter(artifact_dict=model_dict, config=config_basic)
result_basic = converter_basic("test.pdf")

converter_aligned = PdfConverter(artifact_dict=model_dict, config=config_aligned)
result_aligned = converter_aligned("test.pdf")

# 对比
print("基础版识别结果:")
print(result_basic.markdown[:500])

print("\nSurya 对齐版识别结果:")
print(result_aligned.markdown[:500])
```

### 预期改进

**基础版问题**:
```
识别结果:
- Text (正文) ✓
- Text (脚注被误识别为正文) ✗
- Footer (使用了错误的标签) ✗
- 脚注与正文混在一起 ✗
```

**Surya 对齐版**:
```
识别结果:
- Text (正文) ✓
- Footnote (脚注正确识别) ✓
- PageFooter (使用正确标签) ✓
- 脚注与正文正确分离 ✓
```

## 常见问题

### Q1: 为什么需要 Surya 对齐版？

A: Marker 的后续处理模块（如 PageNumberProcessor）是基于 Surya 的行为设计的。如果 VLM 的输出与 Surya 不一致，会导致处理错误。

### Q2: Surya 对齐版与增强版有什么区别？

A:
- **增强版**: 提供详细的块类型描述，但可能与 Surya 的实际行为有差异
- **Surya 对齐版**: 严格遵循 Surya 的标签集、定义和识别习惯，确保兼容性

### Q3: 应该使用哪个版本？

A: **推荐使用 Surya 对齐版**，特别是当：
- 脚注识别出现问题
- 块类型混淆
- 后续处理模块报错
- 需要与 Surya 结果保持一致

### Q4: Surya 对齐版会增加成本吗？

A: 会略微增加 token 数，但提高的准确性值得这个成本。

**Token 对比**:
- 基础版: ~200 tokens
- Surya 对齐版: ~600 tokens
- 增加: ~3倍

### Q5: 如何验证对齐效果？

A: 使用相同文档分别测试 Surya 和 VLM（Surya 对齐版），对比结果：

```python
# Surya
config_surya = {"layout_backend": "surya"}
converter_surya = PdfConverter(artifact_dict=model_dict, config=config_surya)
result_surya = converter_surya("test.pdf")

# VLM (Surya 对齐版)
config_vlm = {
    "layout_backend": "vlm",
    "vlm_layout_prompt_template": "surya_modern",
}
converter_vlm = PdfConverter(artifact_dict=model_dict, config=config_vlm)
result_vlm = converter_vlm("test.pdf")

# 对比块类型分布
from collections import Counter
surya_blocks = Counter([block.block_type for block in result_surya.pages[0].children])
vlm_blocks = Counter([block.block_type for block in result_vlm.pages[0].children])

print("Surya:", surya_blocks)
print("VLM:", vlm_blocks)
```

## 最佳实践

### 1. 根据文档类型选择

- 现代书籍、杂志 → `surya_modern`
- 学术论文、期刊 → `surya_academic`
- 如果不确定 → `surya_modern`（通用）

### 2. 配合其他配置

```python
config = {
    # 版面识别
    "layout_backend": "vlm",
    "vlm_layout_prompt_template": "surya_modern",  # Surya 对齐版
    "vlm_layout_model": "qwen-vl-max",
    "vlm_layout_max_image_dimension": 1536,

    # OCR
    "disable_ocr": True,  # 使用 PDF 文本层

    # 页码提取
    "use_printed_page_number": True,
    "printed_page_zones": ["footer", "header"],
    "page_number_format": "auto",
}
```

### 3. 验证和调试

如果识别效果仍不理想：
1. 检查 VLM 模型能力（推荐 GPT-4o, Claude 3.5, Qwen3-VL-Max）
2. 检查图像质量和分辨率
3. 尝试调整置信度阈值
4. 查看日志，确认使用了正确的模板

## 总结

Surya 对齐版通过严格遵循 Surya 的标签集、块类型定义和识别习惯，确保 VLM 的输出与 Surya 保持一致，解决了脚注识别混乱等问题。

**关键优势**:
- ✅ 完全兼容 Surya 标签集
- ✅ 遵循 Surya 的块类型定义
- ✅ 详细的 Footnote vs PageFooter 区分规则
- ✅ 量化的位置和大小标准
- ✅ 与后续处理模块完全兼容

**推荐配置**:
```python
{
    "layout_backend": "vlm",
    "vlm_layout_prompt_template": "surya_modern",  # 或 surya_academic
    "vlm_layout_model": "qwen-vl-max",
    "disable_ocr": True,
    "use_printed_page_number": True,
}
```
