# 页码锚点和自定义编号诊断报告

## 问题总结

用户遇到的问题：
1. **档案编号提取失败**: 档案有清晰的 "SC 001" 之类的编号，但在 VLM Direct 模式下无法提取
2. **正则表达式不生效**: 设置了正则 `页码[:：]\s*(sc\d+)` 但没有提取成功
3. **UI 配置混乱**: "提取印刷页码" 配置在所有模式下都显示，但可能只在 Pipeline 模式下有效

---

## 核心实现逻辑分析

### 1. 页码锚点系统架构

页码锚点系统包含三个层次：

```
{n}                    ← 定位锚点（0-based 页序，用于区间提取）
<!-- Page: X -->       ← 显示标签（印刷页码或自定义编号）
---                    ← 页面分隔符
```

**示例输出**:
```markdown
{0}

---

<!-- Page: SC 001 -->
第一页内容...

{1}

---

<!-- Page: SC 002 -->
第二页内容...
```

### 2. 自定义编号来源（5种）

| 来源类型 | 说明 | 数据格式 | 适用场景 |
|---------|------|---------|---------|
| **none** | 不使用自定义编号 | - | 默认 |
| **vlm** | VLM 输出提取 | - | VLM 自动识别页码 |
| **file** | 文件上传 | CSV/JSON | 批量导入 |
| **list** | 手动输入列表 | 逗号分隔 | 少量页面 |
| **auto** | 自动生成 | prefix+数字 | 规则编号 |

---

## 问题 1: VLM 输出提取为什么失败？

### 当前实现逻辑

**位置**: `marker/formatters.py:144-209` (PrintedPageExtractor)

```python
class PrintedPageExtractor:
    def __init__(self, patterns=None, remove_from_content=True):
        # 默认模式
        self.patterns = patterns or [
            r'<!--\s*printed-page:\s*([^\s]+)\s*-->',  # <!-- printed-page: XII -->
            r'<!--\s*page:\s*([^\s]+)\s*-->',          # <!-- page: 308 -->
            r'\[页码:\s*([^\]]+)\]',                    # [页码: 12]
        ]
```

### 问题诊断

**你的正则**: `页码[:：]\s*(sc\d+)`

**问题所在**:
1. ❌ **正则没有被使用**: 默认模式是硬编码的，UI 中的正则配置没有传递到 `PrintedPageExtractor`
2. ❌ **VLM 输出格式不匹配**: VLM 不会自动输出 `<!-- printed-page: SC 001 -->` 格式
3. ❌ **提示词没有要求**: VLM 的提示词中没有要求输出页码标记

### 正确的工作流程

要让 VLM 输出提取工作，需要：

1. **在提示词中要求 VLM 输出页码标记**:
```python
prompt = """Convert this page to Markdown.

If you can identify a page number on this page (printed page number,
document ID, or any identifier), please include it at the beginning
in this format:
<!-- page: [identifier] -->

For example:
<!-- page: SC 001 -->
<!-- page: 308 -->
<!-- page: XII -->

Then output the page content in Markdown format.
"""
```

2. **配置正确的提取模式**:
```python
# 在 streamlit_app.py 中
custom_patterns = [
    r'<!--\s*page:\s*([^\s]+)\s*-->',  # 标准格式
    r'页码[:：]\s*(sc\d+)',             # 你的自定义格式
]
```

3. **传递配置到转换器**:
```python
config = {
    "vlm_direct_extract_printed_pages": True,
    "vlm_direct_printed_page_patterns": custom_patterns,  # ← 需要添加这个参数
}
```

---

## 问题 2: 为什么设置正则没有效果？

### 当前代码问题

**位置**: `marker/converters/vlm_direct_async.py:179`

```python
# 初始化印刷页码提取器
self.printed_page_extractor = PrintedPageExtractor() if self.extract_printed_pages else None
```

**问题**:
- ❌ 没有传递自定义正则模式
- ❌ 使用的是硬编码的默认模式
- ❌ UI 中的正则配置没有被读取

### 需要修复的地方

1. **添加配置参数** (`vlm_direct_async.py`):
```python
# 在类定义中添加
vlm_direct_printed_page_patterns: Annotated[list, "自定义页码提取正则模式"] = None

# 在 __init__ 中读取
custom_patterns = config.get("vlm_direct_printed_page_patterns", None)

# 传递给提取器
self.printed_page_extractor = PrintedPageExtractor(
    patterns=custom_patterns
) if self.extract_printed_pages else None
```

2. **在 UI 中添加配置** (`streamlit_app.py`):
```python
if vlm_direct_extract_printed_pages:
    st.text_area(
        "自定义提取正则",
        value=r'<!--\s*page:\s*([^\s]+)\s*-->',
        help="每行一个正则表达式，用于从 VLM 输出中提取页码"
    )
```

---

## 问题 3: "提取印刷页码" 在不同模式下的作用

### Pipeline 模式

**处理器**: `PageNumberProcessor` (marker/processors/page_number.py)

**工作原理**:
1. 使用 Surya OCR 识别页面上的文本
2. 在页面的页眉/页脚区域查找数字
3. 使用启发式规则判断是否为页码
4. 存储到 `page._internal_metadata["printed_page_number"]`

**配置**: `extract_printed_page_numbers` (默认 True)

### VLM Direct 模式

**处理器**: `PrintedPageExtractor` (marker/formatters.py)

**工作原理**:
1. 从 VLM 的 Markdown 输出中提取页码标记
2. 使用正则表达式匹配特定格式
3. 需要 VLM 在输出中包含页码标记

**配置**: `vlm_direct_extract_printed_pages` (默认 True)

### 关键区别

| 维度 | Pipeline 模式 | VLM Direct 模式 |
|------|--------------|----------------|
| **数据来源** | OCR 识别的文本 | VLM 输出的 Markdown |
| **识别方式** | 启发式规则 | 正则表达式匹配 |
| **依赖** | Surya OCR | VLM 提示词 |
| **准确性** | 中等（依赖 OCR） | 高（VLM 理解语义） |
| **成本** | 低（本地 OCR） | 高（API 调用） |

---

## 解决方案

### 方案 A: 使用 VLM 输出提取（推荐）

**优点**: VLM 可以理解语义，识别各种格式的编号

**步骤**:

1. **修改提示词模板** (添加页码识别要求)
2. **修复正则配置传递** (让 UI 配置生效)
3. **测试提取效果**

### 方案 B: 使用自定义编号列表

**优点**: 完全可控，不依赖识别

**步骤**:

1. 设置 `自定义编号来源` = `手动输入列表`
2. 输入: `SC 001, SC 002, SC 003, ...`
3. 系统自动为每页分配编号

### 方案 C: 使用自动生成

**优点**: 适合规则编号

**步骤**:

1. 设置 `自定义编号来源` = `自动生成`
2. 配置: `prefix=SC, start=1, digits=3`
3. 自动生成: SC001, SC002, SC003, ...

---

## UI 配置优化建议

### 当前问题

"页码锚点配置" 在所有模式下都显示，但：
- Pipeline 模式: 使用 `PageNumberProcessor` (OCR 识别)
- VLM Direct 模式: 使用 `PrintedPageExtractor` (正则提取)

两者配置不同，混在一起容易混淆。

### 优化方案

**建议**: 根据转换模式动态显示配置

```python
if converter_type == "Pipeline":
    with st.expander("📍 页码锚点配置"):
        enable_page_anchors = st.checkbox("启用页码锚点", value=True)
        extract_printed_pages = st.checkbox(
            "提取印刷页码",
            value=True,
            help="使用 OCR 从页面图像中识别印刷页码"
        )

elif converter_type == "VLM Direct":
    with st.expander("📍 页码锚点配置"):
        enable_page_anchors = st.checkbox("启用页码锚点", value=True)

        # VLM 输出提取
        extract_from_vlm = st.checkbox(
            "从 VLM 输出提取页码",
            value=False,
            help="需要在提示词中要求 VLM 输出页码标记"
        )

        if extract_from_vlm:
            st.text_area(
                "提取正则表达式",
                value="<!--\\s*page:\\s*([^\\s]+)\\s*-->",
                help="用于从 VLM 输出中提取页码的正则表达式"
            )

        # 自定义编号
        custom_id_source = st.selectbox(
            "自定义编号来源",
            ["无", "手动输入列表", "自动生成", "文件上传"]
        )
```

---

## 总结

### 核心问题

1. ✅ **VLM 输出提取失败**: VLM 没有输出页码标记，且正则配置没有传递
2. ✅ **正则不生效**: 代码中使用硬编码的默认模式，忽略了 UI 配置
3. ✅ **UI 配置混乱**: Pipeline 和 VLM Direct 的页码提取机制不同，但 UI 没有区分

### 推荐解决方案

**对于你的档案编号 "SC 001" 场景**:

**最简单**: 使用 **自动生成** 模式
- 设置: `prefix=SC, start=1, digits=3, 格式=SC 001`
- 无需识别，直接生成

**最准确**: 修复 **VLM 输出提取**
- 修改提示词要求 VLM 输出页码
- 修复正则配置传递
- 测试提取效果

**最可控**: 使用 **手动输入列表**
- 直接输入所有编号
- 适合页数不多的情况

---

## 下一步行动

我可以帮你：

1. ✅ **修复 VLM 输出提取**: 让正则配置生效
2. ✅ **优化 UI 配置**: 根据模式动态显示
3. ✅ **添加自动生成格式化**: 支持 "SC 001" 格式（带空格和前导零）
4. ✅ **创建测试脚本**: 验证提取效果

请告诉我你希望采用哪种方案？
