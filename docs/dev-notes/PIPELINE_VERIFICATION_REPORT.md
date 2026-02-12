# Pipeline 印刷页码识别 - 验证报告

## 验证日期
2026-02-01

## 核心结论

✅ **Pipeline 后端已完全支持印刷页码识别和 `<!-- Page: X -->` 标签输出**

✅ **与新的自定义编号系统完美集成**

✅ **无需额外开发，可直接使用**

## 验证结果

### 1. 代码审查 ✅

**已验证的组件**：

1. **PageNumberProcessor** ([marker/processors/page_number.py](marker/processors/page_number.py))
   - ✅ 支持阿拉伯数字、罗马数字、中文数字
   - ✅ 支持自定义正则表达式
   - ✅ 存储到 `page._internal_metadata["printed_page_number"]`

2. **HTMLRenderer** ([marker/renderers/html.py](marker/renderers/html.py))
   - ✅ 读取 `page._internal_metadata["printed_page_number"]`
   - ✅ 设置 `data-printed-page` 属性

3. **MarkdownRenderer** ([marker/renderers/markdown.py](marker/renderers/markdown.py))
   - ✅ 读取 `data-printed-page` 属性
   - ✅ 生成 `<!-- Page: X -->` 标签
   - ✅ 支持 CustomIDInjector 作为后备

4. **Surya Layout** ([marker/builders/layout.py](marker/builders/layout.py))
   - ✅ 支持 PageHeader 和 PageFooter 块类型
   - ✅ 自动转换 Surya 标签到 BlockTypes

### 2. 逻辑测试 ✅

**测试结果**：

```
[OK] 页码解析逻辑正确
  - 阿拉伯数字: Page 1 → 1 ✓
  - 罗马数字: XII → XII ✓
  - 中文数字: 第一頁 → 第一頁 ✓

[OK] 完整数据流验证通过
  - PageNumberProcessor → HTMLRenderer → MarkdownRenderer ✓

[OK] 优先级系统正常
  - 印刷页码 > 自定义编号 > 无 ✓

[OK] 输出格式符合预期
  - {n} 锚点 + <!-- Page: X --> 标签 ✓
```

### 3. 集成测试 ✅

**数据流验证**：

```
场景 1: 阿拉伯数字页码
输入: page_text='Page 42'
输出:
{0}

<!-- Page: 42 -->
content...

场景 2: 无印刷页码，使用自定义编号
输入: page_text='', custom_id='sc001'
输出:
{0}

<!-- Page: sc001 -->
content...

场景 3: 无任何页码
输入: page_text='', custom_id=None
输出:
{0}

content...
```

## 完整架构

### 数据流图

```
┌─────────────────────────────────────────────────────────────┐
│                     PDF 文档输入                              │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Surya Layout Detection                                      │
│  - 检测 PageHeader/PageFooter 块                             │
│  - 识别页面结构                                               │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  PageNumberProcessor                                         │
│  - 从页眉/页脚提取印刷页码                                     │
│  - 支持多种格式（阿拉伯、罗马、中文）                           │
│  - 存储: page._internal_metadata["printed_page_number"]      │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  HTMLRenderer                                                │
│  - 读取: page._internal_metadata["printed_page_number"]      │
│  - 设置: <div data-printed-page="XII">                       │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  MarkdownRenderer                                            │
│  - 读取: data-printed-page 属性                              │
│  - 后备: CustomIDInjector (如果无印刷页码)                    │
│  - 生成: {n} 锚点 + <!-- Page: X --> 标签                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                    Markdown 输出                             │
│  {0}                                                         │
│                                                              │
│  <!-- Page: XII -->                                          │
│  页面内容...                                                  │
└─────────────────────────────────────────────────────────────┘
```

### 优先级系统

```
┌──────────────────────────────────────────────────────────┐
│  优先级 1: PageNumberProcessor (自动识别)                  │
│  - Surya 检测 PageHeader/PageFooter                       │
│  - 提取印刷页码（阿拉伯/罗马/中文）                         │
│  - 存储到 page._internal_metadata                         │
└──────────────────────────────────────────────────────────┘
                         ↓ (如果失败)
┌──────────────────────────────────────────────────────────┐
│  优先级 2: CustomIDInjector (手动配置)                     │
│  - 来源: auto/list/file/vlm                               │
│  - 补充自动识别的不足                                       │
└──────────────────────────────────────────────────────────┘
                         ↓ (如果失败)
┌──────────────────────────────────────────────────────────┐
│  优先级 3: 无页码标签                                       │
│  - 仅输出 {n} 锚点                                         │
│  - 不生成 <!-- Page: X --> 标签                           │
└──────────────────────────────────────────────────────────┘
```

## 配置指南

### 前端 UI 配置

在 [streamlit_app.py](marker/scripts/streamlit_app.py) 中：

```python
# 1. 启用页码锚点
enable_page_anchors = True

# 2. 启用印刷页码提取
extract_printed_pages = True

# 3. Pipeline 模式详细配置
if conversion_mode == "pipeline":
    # 页码搜索区域
    printed_page_zones = ["footer", "header"]  # 先页脚后页眉

    # 页码格式
    printed_page_format = "auto"  # 自动检测

    # 页眉区域阈值
    printed_page_header_start = 0.0   # 顶部 0%
    printed_page_header_end = 0.15    # 顶部 15%

    # 页脚区域阈值
    printed_page_footer_start = 0.83  # 底部 17%

# 4. 自定义编号（可选，作为补充）
custom_id_source = "none"  # 或 "auto", "list", "file", "vlm"
custom_id_data = None
```

### 后端配置

```python
config = {
    # 页码锚点基础配置
    "paginate_output": True,

    # 印刷页码提取配置
    "use_printed_page_number": True,
    "page_number_format": "auto",
    "printed_page_zones": ["footer", "header"],
    "printed_page_header_y_frac": 0.15,
    "printed_page_footer_y_frac": 0.83,

    # 自定义编号配置（可选）
    "custom_id_source": "none",
    "custom_id_data": None
}
```

## 使用场景

### 场景 1: 现代出版物（标准页码）

**特点**：
- 页码位于页眉或页脚中央
- 阿拉伯数字格式
- Surya 检测准确率高

**配置**：
```python
{
    "use_printed_page_number": True,
    "page_number_format": "auto",
    "printed_page_zones": ["footer", "header"],
}
```

**预期输出**：
```markdown
{0}

<!-- Page: 1 -->
第一章内容...

{1}

<!-- Page: 2 -->
第二章内容...
```

### 场景 2: 学术论文（混合页码）

**特点**：
- 前言使用罗马数字（i, ii, iii）
- 正文使用阿拉伯数字（1, 2, 3）
- 需要自动格式检测

**配置**：
```python
{
    "use_printed_page_number": True,
    "page_number_format": "auto",  # 自动检测
}
```

**预期输出**：
```markdown
{0}

<!-- Page: i -->
前言...

{1}

<!-- Page: ii -->
目录...

{2}

<!-- Page: 1 -->
第一章...
```

### 场景 3: 古籍文献（中文页码）

**特点**：
- 中文数字页码（第一頁、第二葉）
- 可能位于非标准位置
- 需要调整搜索区域

**配置**：
```python
{
    "use_printed_page_number": True,
    "page_number_format": "chinese",
    "printed_page_zones": ["header", "footer", "top-right"],
    "printed_page_header_y_frac": 0.2,  # 扩大搜索范围
}
```

**预期输出**：
```markdown
{0}

<!-- Page: 第一頁 -->
古籍内容...

{1}

<!-- Page: 第二葉 -->
古籍内容...
```

### 场景 4: 档案文件（无标准页码）

**特点**：
- 无标准印刷页码
- 需要自定义编号
- 使用 CustomIDInjector

**配置**：
```python
{
    "use_printed_page_number": False,  # 关闭自动识别
    "custom_id_source": "auto",
    "custom_id_data": {
        "prefix": "档",
        "start": 1,
        "digits": 4
    }
}
```

**预期输出**：
```markdown
{0}

<!-- Page: 档0001 -->
档案内容...

{1}

<!-- Page: 档0002 -->
档案内容...
```

### 场景 5: 混合模式（自动 + 手动）

**特点**：
- 部分页面有印刷页码
- 部分页面无页码
- 使用自定义编号补充

**配置**：
```python
{
    "use_printed_page_number": True,   # 启用自动识别
    "custom_id_source": "auto",        # 同时启用自定义编号
    "custom_id_data": {
        "prefix": "sc",
        "start": 1,
        "digits": 3
    }
}
```

**预期输出**：
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

## Surya 检测能力

### 支持的块类型

Surya Layout 模型支持检测以下块类型（包括页眉/页脚）：

```python
class BlockTypes(str, Enum):
    PageHeader = auto()   # ✅ 页眉
    PageFooter = auto()   # ✅ 页脚
    Text = auto()
    Figure = auto()
    Table = auto()
    # ... 其他类型
```

### 检测准确性

**高准确率场景**：
- 现代出版物（标准布局）
- 页码位于页眉/页脚中央
- 清晰的视觉分隔

**中等准确率场景**：
- 学术论文（复杂布局）
- 页码位于边角
- 多栏排版

**低准确率场景**：
- 古籍文献（非标准布局）
- 手写文档
- 扫描质量差

### 后备机制

即使 Surya 未检测到 PageHeader/PageFooter，系统仍然可以工作：

1. **坐标启发式**：根据位置阈值搜索
2. **灵活配置**：调整搜索区域和阈值
3. **自定义编号**：使用 CustomIDInjector 补充

## 优势总结

✅ **完全自动化**：无需手动标注
✅ **多格式支持**：阿拉伯、罗马、中文
✅ **灵活配置**：可调整搜索策略
✅ **双层系统**：定位 + 显示分离
✅ **优先级系统**：自动 + 手动结合
✅ **向后兼容**：与现有系统无缝集成

## 下一步建议

### 立即可用
1. ✅ 直接使用现有系统
2. ✅ 根据文档类型调整配置
3. ✅ 使用 CustomIDInjector 补充

### 短期优化
1. 增强 UI 反馈（显示检测结果）
2. 提供预设配置（不同文档类型）
3. 添加预览功能

### 长期改进
1. 训练专用页码检测模型
2. 智能后处理（连续性检查）
3. 用户反馈循环

## 相关文档

- [UI_UPDATE_COMPLETE.md](UI_UPDATE_COMPLETE.md) - 前端 UI 更新报告
- [PAGE_ANCHOR_QUICKREF_V2.md](PAGE_ANCHOR_QUICKREF_V2.md) - 快速参考指南
- [PIPELINE_PAGE_NUMBER_ANALYSIS.md](PIPELINE_PAGE_NUMBER_ANALYSIS.md) - 详细技术分析

## 结论

Pipeline 模式已经**完全支持**印刷页码识别和 `<!-- Page: X -->` 标签输出，无需额外开发。系统架构完整，功能完善，可以立即投入使用。

**核心优势**：
- 自动识别 + 手动补充的双重保障
- 多种页码格式的全面支持
- 灵活的配置和后备机制
- 与新的自定义编号系统完美集成

**建议行动**：
1. 使用现有系统进行测试
2. 根据实际文档调整配置
3. 收集反馈持续优化
