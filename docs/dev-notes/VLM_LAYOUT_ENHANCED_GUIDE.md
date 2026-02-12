# VLM 版面识别增强提示词使用指南

## 问题背景

使用 VLM (如 Qwen3-VL-Max) 进行版面识别时，虽然模型能力很强，但识别效果不理想，特别是：
- **脚注识别混乱**: 脚注与正文混淆
- **块类型不准确**: PageFooter 与 Footnote 混淆
- **边界不精确**: 块的边界框不够准确

**根本原因**: 提示词过于简单，只列出标签名称，没有详细说明每种块类型的视觉特征和区分规则。

## 解决方案

创建了**增强版提示词模板**，包含：
1. 详细的块类型规范（视觉特征、位置、大小）
2. 块类型之间的区分规则
3. 识别优先级和策略
4. 文档类型特定的规则

## 使用方法

### 方法 1: 在配置中指定增强版模板

```python
config = {
    "layout_backend": "vlm",
    "vlm_layout_prompt_template": "modern_enhanced",  # 使用增强版
    "ocr_backend": "surya",
    "disable_ocr": True,
    "use_printed_page_number": True,
}

converter = PdfConverter(artifact_dict=model_dict, config=config)
result = converter("document.pdf")
```

### 方法 2: 在 Streamlit UI 中选择

在"版面识别后端"配置中：
1. 选择 "VLM（视觉语言模型）"
2. 在"提示词模板"下拉菜单中选择：
   - `modern_enhanced` - 现代出版物（增强版）
   - `academic_enhanced` - 学术论文（增强版）
   - `chinese_ancient_enhanced` - 中文古籍（增强版）

## 可用的增强版模板

### 1. modern_enhanced (现代出版物 - 增强版)

**适用场景**:
- 现代书籍、杂志
- 有脚注的文档
- 标准排版的出版物

**增强特性**:
- 详细的 Footnote 识别规则（位置、大小、标记）
- PageFooter vs Footnote 的明确区分
- 基于位置和大小的分类规则

**示例配置**:
```python
{
    "vlm_layout_prompt_template": "modern_enhanced",
}
```

### 2. academic_enhanced (学术论文 - 增强版)

**适用场景**:
- 学术论文、期刊文章
- 脚注密集的文档
- 多栏布局
- 包含公式、图表的文档

**增强特性**:
- 针对学术论文的脚注识别（密集、编号连续）
- 多栏布局处理规则
- 公式、图表、标题的精确识别
- References vs Footnote 的区分

**示例配置**:
```python
{
    "vlm_layout_prompt_template": "academic_enhanced",
}
```

### 3. chinese_ancient_enhanced (中文古籍 - 增强版)

**适用场景**:
- 中文古籍、善本
- 竖排文字
- 有夹注、眉批的文档

**增强特性**:
- 夹注（小字注释）的精确识别
- 竖排文字的处理规则
- 古籍特有元素（印章、题跋、批注）
- 版心、边框等传统元素

**示例配置**:
```python
{
    "vlm_layout_prompt_template": "chinese_ancient_enhanced",
}
```

## 增强版 vs 基础版对比

### 基础版提示词
```
For each region you detect, provide:
- label: The type of content. Must be one of: Text, SectionHeader, ..., Footnote, ...
- polygon: Bounding box coordinates
- confidence: Confidence score
```

**问题**: 只列出标签，没有说明什么是 Footnote

### 增强版提示词
```
### Footnote (脚注) - IMPORTANT
**Visual Characteristics**:
- Location: Bottom 10-20% of page
- Font size: 70-80% of main text size (noticeably smaller)
- Markers: Has numbering (<sup>1)</sup>, [1], ①, *)
- Separation: Separated from main text by horizontal line or significant whitespace

**Key Distinctions**:
- vs Text: Smaller font, bottom location, has markers
- vs PageFooter: Footnote has annotation content with markers; PageFooter has page numbers/metadata
```

**优势**: 详细说明了 Footnote 的特征和区分规则

## 效果对比

### 使用基础版
```
识别结果:
- Text (正文) ✓
- Text (脚注被误识别为正文) ✗
- PageFooter (页码) ✓
```

### 使用增强版
```
识别结果:
- Text (正文) ✓
- Footnote (脚注正确识别) ✓
- PageFooter (页码) ✓
```

## 关键改进点

### 1. Footnote 识别规则

**位置规则**:
- 现代出版物: 底部 10-20%
- 学术论文: 底部 15-25%（脚注更密集）
- 古籍: 行间或边缘（夹注）

**大小规则**:
- 现代出版物: 70-80% 正文大小
- 学术论文: 60-75% 正文大小
- 古籍: 50-60% 正文大小

**标记规则**:
- 有编号: <sup>1)</sup>, [1], ①, *
- 与正文有分隔线或空白

### 2. 块类型区分规则

**Footnote vs PageFooter**:
- Footnote: 注释内容，有编号标记，较长
- PageFooter: 页码/元信息，简短

**Footnote vs Text**:
- Footnote: 字号更小，位于底部，有标记
- Text: 标准字号，主体区域

**Footnote vs Caption**:
- Footnote: 页面底部
- Caption: 紧邻图表

### 3. 识别优先级

```
1. 先识别 PageHeader 和 PageFooter（顶部/底部边缘）
2. 再识别 Footnote（底部区域，有标记）
3. 最后识别主体内容（Text, SectionHeader 等）
```

## 测试验证

### 测试脚本

```python
from marker.converters.pdf import PdfConverter
from marker.models import create_model_dict
import re

# 基础版测试
config_basic = {
    "layout_backend": "vlm",
    "vlm_layout_prompt_template": "modern",  # 基础版
    "disable_ocr": True,
    "use_printed_page_number": True,
}

# 增强版测试
config_enhanced = {
    "layout_backend": "vlm",
    "vlm_layout_prompt_template": "modern_enhanced",  # 增强版
    "disable_ocr": True,
    "use_printed_page_number": True,
}

model_dict = create_model_dict()

# 测试基础版
converter_basic = PdfConverter(artifact_dict=model_dict, config=config_basic)
result_basic = converter_basic("test.pdf")

# 测试增强版
converter_enhanced = PdfConverter(artifact_dict=model_dict, config=config_enhanced)
result_enhanced = converter_enhanced("test.pdf")

# 对比结果
print("基础版:")
print(f"  页码标签: {len(re.findall(r'<!-- Page:', str(result_basic)))}")

print("增强版:")
print(f"  页码标签: {len(re.findall(r'<!-- Page:', str(result_enhanced)))}")
```

### 评估指标

1. **Footnote 识别准确率**: 正确识别的脚注数 / 实际脚注数
2. **Footnote vs Text 混淆率**: 被误识别为 Text 的脚注数 / 实际脚注数
3. **PageFooter vs Footnote 混淆率**: 被误识别为 PageFooter 的脚注数 / 实际脚注数

## 常见问题

### Q1: 增强版会增加 API 成本吗？

A: 会略微增加，因为提示词更长。但提高的准确率通常值得这个成本。

**成本对比**:
- 基础版: ~200 tokens
- 增强版: ~800 tokens
- 增加: ~4倍 token 数

**建议**: 对于脚注密集或要求高精度的文档使用增强版，普通文档可使用基础版。

### Q2: 如何选择合适的模板？

**决策树**:
```
文档有大量脚注？
├─ 是 → 使用增强版
│   ├─ 学术论文 → academic_enhanced
│   ├─ 现代书籍 → modern_enhanced
│   └─ 中文古籍 → chinese_ancient_enhanced
└─ 否 → 使用基础版
    ├─ 现代文档 → modern
    ├─ 古籍 → chinese_ancient
    └─ 其他 → 根据文档类型选择
```

### Q3: 增强版还是识别不准确怎么办？

**排查步骤**:
1. 检查 VLM 模型能力（推荐 GPT-4o, Claude 3.5, Qwen3-VL-Max）
2. 检查图像质量（分辨率、清晰度）
3. 尝试调整配置参数（置信度阈值）
4. 考虑使用自定义提示词

**自定义提示词**:
```python
config = {
    "layout_backend": "vlm",
    "vlm_layout_prompt": "你的自定义提示词...",  # 直接指定
}
```

### Q4: 可以同时使用多个模板吗？

A: 不可以。每次只能使用一个模板。但可以为不同的文档使用不同的模板。

## 最佳实践

### 1. 根据文档类型选择模板

- 学术论文、期刊 → `academic_enhanced`
- 现代书籍、杂志 → `modern_enhanced`
- 中文古籍 → `chinese_ancient_enhanced`
- 普通文档 → `modern`（基础版）

### 2. 配合其他配置优化

```python
config = {
    # 版面识别
    "layout_backend": "vlm",
    "vlm_layout_prompt_template": "modern_enhanced",
    "vlm_layout_max_image_dimension": 1536,  # 图像分辨率
    "vlm_layout_confidence_threshold": 0.7,  # 置信度阈值

    # OCR
    "disable_ocr": True,  # 使用 PDF 文本层

    # 页码提取
    "use_printed_page_number": True,
    "printed_page_zones": ["footer", "header"],
    "page_number_format": "auto",
}
```

### 3. 迭代优化

1. 先用基础版测试
2. 如果脚注识别不准确，切换到增强版
3. 如果还不满意，考虑自定义提示词
4. 收集反馈，持续优化

## 总结

增强版提示词通过详细的块类型规范和识别规则，显著提高了 VLM 版面识别的准确性，特别是对于脚注密集的文档。

**关键优势**:
- ✅ 详细的 Footnote 识别规则
- ✅ 明确的块类型区分标准
- ✅ 基于位置和大小的分类策略
- ✅ 文档类型特定的优化

**使用建议**:
- 脚注密集文档 → 使用增强版
- 普通文档 → 使用基础版
- 根据实际效果调整选择
