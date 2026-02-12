# 边码识别功能使用指南

## 功能概述

本功能为 Marker CUDA 添加了两种新的版面识别类型，专门用于识别中文古籍和西方经典文献中的边码元素：

1. **MarginalAnnotation（边码/页边注）** - 识别页面边缘的注释和编码
2. **InlineAnnotation（行内小字注）** - 识别正文中的小字注释

## 新增的 BlockTypes

### 1. MarginalAnnotation

**涵盖内容**：
- 中文古籍版心（书名、卷次、叶码）
- 鱼尾装饰符
- Stephanus 编码（柏拉图全集，如 "514a"）
- Bekker 编码（亚里士多德全集，如 "1047a8"）
- 行号（Critical Edition）
- 书耳
- 眉批/批注

**元数据字段**：
- `marginal_subtype`: 细分类型（版心叶码/行号/Stephanus编码/Bekker编码/书耳/眉批/鱼尾）
- `position_type`: 位置类型（left_margin/right_margin/top_margin/bottom_margin/vertical_center）

### 2. InlineAnnotation

**涵盖内容**：
- 双行小字
- 夹注
- 割注
- 括号包裹的短注释

**元数据字段**：
- `inline_subtype`: 细分类型（双行小字/夹注/割注/括号注）
- `font_size_ratio`: 字体大小与主文本的比例
- `is_parenthetical`: 是否为括号包裹

## 使用方法

### 方法 1：在 PDF 转换流程中启用

在转换配置中添加处理器：

```python
from marker.converters.pdf import PdfConverter
from marker.processors.marginal_annotation import MarginalAnnotationProcessor
from marker.processors.inline_annotation import InlineAnnotationProcessor

# 创建转换器
converter = PdfConverter()

# 添加边码识别处理器
converter.processors.append(MarginalAnnotationProcessor(config={
    "enable_marginal_detection": True,
    "left_margin_threshold": 0.15,  # 左边栏阈值
    "right_margin_threshold": 0.85,  # 右边栏阈值
    "top_margin_threshold": 0.10,    # 上边栏阈值
}))

# 添加行内注释识别处理器
converter.processors.append(InlineAnnotationProcessor(config={
    "enable_inline_detection": True,
    "font_size_ratio_threshold": 0.75,  # 字体比例阈值
    "max_inline_annotation_length": 100,  # 最大注释长度
}))

# 转换文档
document = converter(pdf_path)
```

### 方法 2：在 Streamlit 界面中配置

在 `marker/scripts/streamlit_app.py` 中添加配置选项：

```python
# 边码识别配置
enable_marginal = st.checkbox("Enable Marginal Annotation Detection", value=False)
if enable_marginal:
    left_threshold = st.slider("Left Margin Threshold", 0.0, 0.5, 0.15)
    right_threshold = st.slider("Right Margin Threshold", 0.5, 1.0, 0.85)

    config["marginal_annotation"] = {
        "enable_marginal_detection": True,
        "left_margin_threshold": left_threshold,
        "right_margin_threshold": right_threshold,
    }
```

### 方法 3：命令行使用

```bash
python convert_single.py input.pdf output.md \
    --enable_marginal_detection \
    --left_margin_threshold 0.15 \
    --enable_inline_detection \
    --font_size_ratio_threshold 0.75
```

## 识别规则说明

### MarginalAnnotationProcessor 规则

#### 位置判断
- **左边栏**: 中心点 X < 页面宽度 × 0.15
- **右边栏**: 中心点 X > 页面宽度 × 0.85
- **上边栏**: 中心点 Y < 页面高度 × 0.10
- **下边栏**: 中心点 Y > 页面高度 × 0.90
- **垂直中线**: |中心点 X - 页面宽度/2| < 页面宽度 × 0.05

#### 内容判断
1. **版心叶码**: 垂直中线 + 包含"卷"/"叶"/"第"/"页"
2. **Stephanus 编码**: 边栏 + 匹配 `\d{3,4}[a-e]\d*` 格式
3. **Bekker 编码**: 左边栏 + 匹配 `\d{4}[ab]\d+` 格式
4. **行号**: 边栏 + 纯数字 + 长度 ≤ 4
5. **书耳**: 上边栏 + 文本长度 < 20
6. **眉批**: 上边栏 + 文本长度 20-100

#### 字体判断
- 字体大小 < 主文本 × 0.8 且在边缘位置

### InlineAnnotationProcessor 规则

#### 字体大小判断
- 平均字体大小 / 主文本字体大小 < 0.75

#### 格式判断
- 包含 "small" 格式标记

#### 括号判断
- 文本被括号包裹：()、（）、[]、【】、{}、〔〕、〈〉、《》

#### 双行小字判断
- 同一块内有多个 span，字体大小差异 > 30%

## 输出格式

### JSON 输出

```json
{
  "block_type": "MarginalAnnotation",
  "html": "<aside class=\"marginal-annotation\" data-subtype=\"行号\" data-position=\"left_margin\">5</aside>",
  "polygon": [[10, 100], [30, 100], [30, 120], [10, 120]],
  "metadata": {
    "marginal_subtype": "行号",
    "position_type": "left_margin"
  }
}
```

### Markdown 输出

边码会被渲染为 HTML aside 标签：

```html
<aside class="marginal-annotation" data-subtype="行号" data-position="left_margin">5</aside>
```

行内注释会被渲染为 HTML span 标签：

```html
<span class="inline-annotation" data-subtype="夹注" data-font-ratio="0.65">注释文本</span>
```

## 配置参数详解

### MarginalAnnotationProcessor

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enable_marginal_detection` | bool | True | 是否启用边码检测 |
| `left_margin_threshold` | float | 0.15 | 左边栏阈值（页面宽度比例） |
| `right_margin_threshold` | float | 0.85 | 右边栏阈值（页面宽度比例） |
| `top_margin_threshold` | float | 0.10 | 上边栏阈值（页面高度比例） |
| `bottom_margin_threshold` | float | 0.90 | 下边栏阈值（页面高度比例） |
| `vertical_center_tolerance` | float | 0.05 | 垂直中线容差（页面宽度比例） |

### InlineAnnotationProcessor

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enable_inline_detection` | bool | True | 是否启用行内注释检测 |
| `font_size_ratio_threshold` | float | 0.75 | 字体大小比例阈值 |
| `max_inline_annotation_length` | int | 100 | 行内注释的最大字符数 |

## 测试

运行测试脚本验证功能：

```bash
python test_blocktypes_simple.py
```

预期输出：
```
[SUCCESS] BlockTypes verification passed!

New block types added:
  1. MarginalAnnotation - For marginal notes, page numbers, line numbers
  2. InlineAnnotation - For inline small-text annotations
```

## 文件清单

### 核心文件
1. `marker/schema/__init__.py` - 添加了新的 BlockTypes
2. `marker/services/layout_base.py` - 更新了 SUPPORTED_LAYOUT_LABELS
3. `marker/schema/blocks/marginalannotation.py` - MarginalAnnotation 块类
4. `marker/schema/blocks/inlineannotation.py` - InlineAnnotation 块类
5. `marker/schema/registry.py` - 注册新块类型
6. `marker/processors/marginal_annotation.py` - 边码识别处理器
7. `marker/processors/inline_annotation.py` - 行内注释识别处理器

### 测试文件
1. `test_blocktypes_simple.py` - 简化测试脚本
2. `test_marginal_annotation.py` - 完整测试脚本（需要完整依赖）

## 注意事项

1. **处理器顺序**: 边码识别处理器应该在 OCR 之后、最终渲染之前运行
2. **性能影响**: 处理器会遍历所有文本块，对大文档可能有轻微性能影响
3. **误识别**: 某些正常文本可能被误识别为边码，可以通过调整阈值参数来优化
4. **字体信息依赖**: 行内注释识别依赖 OCR 提供的字体大小信息，某些 OCR 方法可能不提供此信息

## 未来改进方向

1. **机器学习模型**: 使用训练好的模型替代规则判断，提高准确率
2. **更多边码类型**: 支持更多文献类型的边码格式
3. **自适应阈值**: 根据文档特征自动调整阈值参数
4. **UI 集成**: 在 Streamlit 界面中添加可视化配置和预览

## 技术支持

如有问题或建议，请提交 Issue 或 Pull Request。
