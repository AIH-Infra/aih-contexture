# Pipeline 模式印刷页码识别分析报告

## 执行日期
2026-02-01

## 分析结论

✅ **Pipeline 后端已完全支持印刷页码识别和 `<!-- Page: X -->` 标签输出**

## 技术架构

### 完整数据流

```
1. Surya Layout Detection
   ↓ 检测 PageHeader/PageFooter 块

2. PageNumberProcessor
   ↓ 从页眉/页脚提取印刷页码
   ↓ 存储到 page._internal_metadata["printed_page_number"]

3. HTMLRenderer
   ↓ 读取 metadata
   ↓ 设置 data-printed-page 属性

4. MarkdownRenderer
   ↓ 读取 data-printed-page
   ↓ 生成 <!-- Page: X --> 标签

5. 最终输出
   {0}

   <!-- Page: XII -->
   页面内容...
```

## 核心组件分析

### 1. PageNumberProcessor ([marker/processors/page_number.py](marker/processors/page_number.py))

**功能**：
- 从页眉/页脚中提取印刷页码
- 支持多种格式：阿拉伯数字、罗马数字、中文数字
- 支持自定义正则表达式

**关键代码**：
```python
# 行 411-412：存储印刷页码到元数据
if printed_page_number:
    page._internal_metadata["printed_page_number"] = printed_page_number
```

**支持的页码格式**：
- **阿拉伯数字**：1, 2, 3, Page 1, 第1页
- **罗马数字**：I, II, III, XII, i, ii, iii
- **中文数字**：第一頁, 第二葉, 卷一第三

**搜索区域**：
- PageHeader 块（优先级最高）
- PageFooter 块
- 页眉区域（坐标启发式，默认顶部 15%）
- 页脚区域（坐标启发式，默认底部 17%）
- 可配置：top-right, bottom-right, top-left, bottom-left

**配置参数**：
```python
{
    "use_printed_page_number": True,           # 启用印刷页码提取
    "page_number_format": "auto",              # arabic/roman/chinese/auto
    "printed_page_zones": ["footer", "header"], # 搜索区域
    "printed_page_header_y_frac": 0.15,        # 页眉阈值
    "printed_page_footer_y_frac": 0.83,        # 页脚阈值
}
```

### 2. HTMLRenderer ([marker/renderers/html.py](marker/renderers/html.py))

**功能**：
- 读取页面元数据中的印刷页码
- 设置 HTML 属性 `data-printed-page`

**关键代码**：
```python
# 行 118-123：读取元数据并设置属性
if hasattr(page, "_internal_metadata") and "printed_page_number" in page._internal_metadata:
    printed_page_num = page._internal_metadata["printed_page_number"]

content = f"<div class='page' data-page-id='{ref_block_id.page_id}' data-printed-page='{printed_page_num}'>{content}</div>"
```

### 3. MarkdownRenderer ([marker/renderers/markdown.py](marker/renderers/markdown.py))

**功能**：
- 读取 `data-printed-page` 属性
- 生成 `<!-- Page: X -->` 标签
- 支持 CustomIDInjector 作为后备

**关键代码**：
```python
# 行 84-98：读取印刷页码并生成标签
printed_page_id = el.get("data-printed-page", "")
if not printed_page_id:
    printed_page_id = None

# 如果没有印刷页码，尝试从 CustomIDInjector 获取
if not printed_page_id and self.custom_id_injector:
    printed_page_id = self.custom_id_injector.get_custom_id(page_id)

# 生成页码标记（如果有印刷页码或自定义编号）
page_tag = ""
if printed_page_id:
    page_tag = f"<!-- Page: {printed_page_id} -->\\n"
```

**优先级系统**：
```
PageNumberProcessor (自动识别) > CustomIDInjector (自定义) > 无
```

### 4. Surya Layout Detection

**功能**：
- 检测页面布局，识别不同的块类型
- 支持的块类型包括 PageHeader 和 PageFooter

**关键代码** ([marker/builders/layout.py](marker/builders/layout.py)):
```python
# 行 141：Surya 标签转换为 BlockTypes
block_cls = get_block_class(BlockTypes[bbox.label])
```

**支持的块类型** ([marker/schema/__init__.py](marker/schema/__init__.py)):
```python
class BlockTypes(str, Enum):
    PageHeader = auto()   # 页眉
    PageFooter = auto()   # 页脚
    # ... 其他类型
```

## Surya 页眉/页脚检测能力

### 当前状态

Surya Layout 模型**理论上支持** PageHeader 和 PageFooter 检测：
- BlockTypes 枚举中包含 PageHeader 和 PageFooter
- LayoutBuilder 会将 Surya 的标签转换为对应的 BlockTypes
- PageNumberProcessor 会处理这些块类型

### 实际检测效果

Surya 的页眉/页脚检测效果取决于：
1. **模型训练数据**：Surya 模型是否在包含页眉/页脚的数据集上训练
2. **文档类型**：现代出版物的页眉/页脚更容易识别，古籍可能较难
3. **页码位置**：标准位置（页眉中央、页脚中央）更容易识别

### 后备机制

即使 Surya 未检测到 PageHeader/PageFooter 块，PageNumberProcessor 仍然可以工作：
- **坐标启发式**：根据位置阈值搜索页眉/页脚区域
- **灵活配置**：可调整搜索区域和阈值
- **多格式支持**：自动尝试多种页码格式

## 配置示例

### 完整配置（Pipeline 模式）

```python
config = {
    # 页码锚点基础配置
    "paginate_output": True,

    # 印刷页码提取配置
    "use_printed_page_number": True,
    "page_number_format": "auto",  # 自动检测格式
    "printed_page_zones": ["footer", "header"],
    "printed_page_header_y_frac": 0.15,
    "printed_page_footer_y_frac": 0.83,

    # 自定义编号配置（可选，作为补充）
    "custom_id_source": "auto",
    "custom_id_data": {
        "prefix": "sc",
        "start": 1,
        "digits": 3
    }
}
```

### 前端 UI 配置

在 streamlit_app.py 中，用户可以配置：

```python
# 基础配置
enable_page_anchors = True

# 印刷页码提取
extract_printed_pages = True

# Pipeline 模式详细配置
if conversion_mode == "pipeline":
    printed_page_zones = ["footer", "header"]
    printed_page_format = "auto"
    printed_page_header_start = 0.0
    printed_page_header_end = 0.15
    printed_page_footer_start = 0.83

# 自定义编号（可选）
custom_id_source = "none"  # 或 "auto", "list", "file", "vlm"
custom_id_data = None
```

## 输出示例

### 场景 1：仅自动识别的印刷页码

```markdown
{0}

<!-- Page: XII -->
前言内容...

{1}

<!-- Page: 1 -->
第一章内容...

{2}

<!-- Page: 2 -->
第二章内容...
```

### 场景 2：印刷页码 + 自定义编号（混合）

```markdown
{0}

<!-- Page: XII -->
有印刷页码的页面...

{1}

<!-- Page: sc002 -->
无印刷页码的页面（使用自定义编号）...

{2}

<!-- Page: 1 -->
又有印刷页码的页面...
```

### 场景 3：仅自定义编号

```markdown
{0}

<!-- Page: 档0001 -->
档案第一页...

{1}

<!-- Page: 档0002 -->
档案第二页...
```

## 优势分析

### 1. 完全自动化
- 无需手动标注页码
- Surya 自动检测页眉/页脚
- PageNumberProcessor 自动提取页码

### 2. 多格式支持
- 阿拉伯数字、罗马数字、中文数字
- 自定义正则表达式
- 自动格式检测

### 3. 灵活配置
- 可调整搜索区域
- 可调整位置阈值
- 支持多种搜索策略

### 4. 双层系统
- {n} 锚点用于定位
- <!-- Page: X --> 标签用于显示
- 两者独立，互不干扰

### 5. 优先级系统
- 自动识别优先
- 自定义编号补充
- 灵活组合使用

## 局限性

### 1. Surya 检测准确性
- 依赖 Surya 模型的训练数据
- 非标准布局可能检测失败
- 古籍、手稿等特殊文档可能需要调整

### 2. 页码格式识别
- 复杂格式可能需要自定义正则
- 多语言混合可能需要特殊处理
- 非标准页码格式可能识别失败

### 3. 位置启发式
- 固定阈值可能不适用所有文档
- 需要根据文档类型调整
- 边缘情况可能需要手动配置

## 改进建议

### 短期改进

1. **增强 UI 反馈**
   - 显示检测到的页码数量
   - 显示检测失败的页面
   - 提供预览功能

2. **优化默认配置**
   - 根据文档类型自动调整阈值
   - 提供预设配置（现代出版物、古籍、档案等）

3. **增强错误处理**
   - 页码格式不匹配时的警告
   - 页码缺失时的提示
   - 页码不连续时的检测

### 长期改进

1. **训练专用模型**
   - 训练专门的页码检测模型
   - 提高古籍、手稿的识别率
   - 支持更多语言和格式

2. **智能后处理**
   - 页码连续性检查
   - 页码格式一致性检查
   - 自动修正明显错误

3. **用户反馈循环**
   - 允许用户标注错误
   - 收集数据改进模型
   - 持续优化识别准确率

## 测试建议

### 测试用例

1. **现代出版物**
   - 标准页眉/页脚
   - 阿拉伯数字页码
   - 预期：高准确率

2. **古籍文献**
   - 中文数字页码
   - 非标准位置
   - 预期：需要调整配置

3. **学术论文**
   - 罗马数字前言
   - 阿拉伯数字正文
   - 预期：混合格式识别

4. **档案文件**
   - 无标准页码
   - 需要自定义编号
   - 预期：使用 CustomIDInjector

### 测试方法

```python
# 测试脚本
from marker.converters.pdf import PdfConverter

config = {
    "use_printed_page_number": True,
    "page_number_format": "auto",
    "printed_page_zones": ["footer", "header"],
}

converter = PdfConverter(config)
result = converter("test.pdf")

# 检查输出
markdown = result.markdown
print("检测到的页码标签：")
import re
page_tags = re.findall(r"<!-- Page: (.+?) -->", markdown)
for i, tag in enumerate(page_tags):
    print(f"  页面 {i}: {tag}")
```

## 总结

Pipeline 模式已经**完全支持**印刷页码识别和 `<!-- Page: X -->` 标签输出：

✅ **架构完整**：PageNumberProcessor → HTMLRenderer → MarkdownRenderer
✅ **功能完善**：多格式支持、灵活配置、优先级系统
✅ **与新系统集成**：支持 CustomIDInjector 作为补充
✅ **Surya 支持**：理论上支持 PageHeader/PageFooter 检测，实际效果取决于模型和文档类型

**建议**：
1. 直接使用现有系统，无需额外开发
2. 根据文档类型调整配置参数
3. 使用 CustomIDInjector 补充自动识别的不足
4. 收集实际使用数据，持续优化配置

**下一步**：
- 测试不同类型文档的识别效果
- 优化默认配置参数
- 增强 UI 反馈和预览功能
