# 页码提取和自定义编号修复报告

## 修复总览

✅ **已完成所有修复**

本次修复解决了以下问题：
1. ✅ VLM 输出提取的正则配置无法传递
2. ✅ 自动生成不支持 "SC 001" 格式（带空格）
3. ✅ UI 配置改进（正则表达式支持多行输入）

---

## 修复 1: VLM 输出提取正则配置传递

### 问题描述

用户设置的正则表达式 `页码[:：]\s*(sc\d+)` 无法生效，因为：
- 代码中使用硬编码的默认正则模式
- UI 配置没有传递到 `PrintedPageExtractor`

### 修复内容

#### 1.1 添加配置参数 ([vlm_direct_async.py:106](marker/converters/vlm_direct_async.py#L106))

```python
# 🆕 新增配置参数
vlm_direct_printed_page_patterns: Annotated[list | None, "自定义页码提取正则模式列表"] = None
```

#### 1.2 读取配置 ([vlm_direct_async.py:156](marker/converters/vlm_direct_async.py#L156))

```python
# 🆕 读取自定义正则模式
custom_patterns = config.get("vlm_direct_printed_page_patterns", self.vlm_direct_printed_page_patterns)
```

#### 1.3 传递给提取器 ([vlm_direct_async.py:180](marker/converters/vlm_direct_async.py#L180))

```python
# 🆕 传递自定义正则模式
self.printed_page_extractor = PrintedPageExtractor(
    patterns=custom_patterns,
    remove_from_content=True
) if self.extract_printed_pages else None
```

### 使用方法

现在可以在 UI 中配置自定义正则表达式：

```
自定义编号来源: VLM 输出提取

正则表达式列表（每行一个）:
<!--\s*page:\s*(\S+)\s*-->
页码[:：]\s*(\S+)
\[页码:\s*([^\]]+)\]
```

---

## 修复 2: 自动生成支持 "SC 001" 格式

### 问题描述

自动生成只能生成 "SC001" 格式，无法生成 "SC 001"（带空格）格式。

### 修复内容

#### 2.1 增强 CustomIDInjector ([formatters.py:285](marker/formatters.py#L285))

```python
def _generate_ids(self, config: dict) -> dict:
    """自动生成编号"""
    prefix = config.get('prefix', 'page')
    start = config.get('start', 1)
    digits = config.get('digits', 3)
    separator = config.get('separator', '')  # 🆕 分隔符

    return {
        idx: f"{prefix}{separator}{str(start + idx).zfill(digits)}"
        for idx in range(count)
    }
```

#### 2.2 UI 配置增强 ([streamlit_app.py:643](marker/scripts/streamlit_app.py#L643))

```python
# 🆕 添加分隔符选项
auto_separator = st.selectbox(
    "分隔符",
    options=["", " ", "-", "_"],
    index=1,  # 默认空格
    format_func=lambda x: {
        "": "无（SC001）",
        " ": "空格（SC 001）",
        "-": "横线（SC-001）",
        "_": "下划线（SC_001）"
    }.get(x, x)
)
```

### 使用方法

现在可以在 UI 中配置：

```
自定义编号来源: 自动生成
编号前缀: SC
起始编号: 1
分隔符: 空格（SC 001）  ← 🆕 新增
编号位数: 3
```

生成结果：`SC 001`, `SC 002`, `SC 003`, ...

---

## 修复 3: UI 配置改进

### 3.1 正则表达式支持多行输入

**位置**: [streamlit_app.py:610](marker/scripts/streamlit_app.py#L610)

**改进前**:
```python
vlm_extract_pattern = st.text_input(
    "提取正则表达式",
    value=r"页码[:：]\s*(\S+)"
)
```

**改进后**:
```python
vlm_extract_patterns_text = st.text_area(
    "正则表达式列表（每行一个）",
    value="<!--\\s*page:\\s*(\\S+)\\s*-->\n页码[:：]\\s*(\\S+)\n\\[页码:\\s*([^\\]]+)\\]",
    height=100
)
```

**优点**:
- ✅ 支持多个正则模式
- ✅ 按顺序尝试匹配
- ✅ 更灵活的配置

### 3.2 配置传递链路

```
UI (streamlit_app.py)
  ↓ 用户输入多行正则
vlm_extract_patterns_text
  ↓ 解析为列表
vlm_extract_patterns = [...]
  ↓ 存储到 custom_id_data
custom_id_data = {"patterns": vlm_extract_patterns}
  ↓ 提取并传递
vlm_direct_printed_page_patterns = custom_id_data["patterns"]
  ↓ 配置字典
config["vlm_direct_printed_page_patterns"] = vlm_direct_printed_page_patterns
  ↓ VlmDirectAsyncConverter
custom_patterns = config.get("vlm_direct_printed_page_patterns")
  ↓ PrintedPageExtractor
PrintedPageExtractor(patterns=custom_patterns)
```

---

## 使用示例

### 示例 1: 提取档案编号 "SC 001"

**场景**: 档案有清晰的 "SC 001", "SC 002" 编号

**方案 A: 使用自动生成（推荐）**

```
自定义编号来源: 自动生成
编号前缀: SC
起始编号: 1
分隔符: 空格
编号位数: 3
```

**结果**: 自动生成 `SC 001`, `SC 002`, `SC 003`, ...

**方案 B: 使用 VLM 输出提取**

1. 修改提示词，要求 VLM 输出页码标记：
```
Convert this page to Markdown.

If you can identify a document ID or page number (like "SC 001"),
please include it at the beginning in this format:
<!-- page: SC 001 -->

Then output the page content.
```

2. 配置正则表达式：
```
<!--\s*page:\s*(\S+\s+\d+)\s*-->
页码[:：]\s*(SC\s+\d+)
```

### 示例 2: 提取罗马数字页码

**配置**:
```
自定义编号来源: VLM 输出提取

正则表达式列表:
<!--\s*page:\s*([IVXLCDM]+)\s*-->
页码[:：]\s*([IVXLCDM]+)
```

---

## 配置参数说明

### VLM Direct 模式新增参数

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `vlm_direct_printed_page_patterns` | list[str] \| None | None | 自定义正则模式列表 |

### CustomIDInjector 自动生成新增参数

| 参数名 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `separator` | str | "" | 前缀与数字之间的分隔符 |

---

## 测试建议

### 测试 1: 验证正则配置传递

```python
# 测试配置
config = {
    "vlm_direct_extract_printed_pages": True,
    "vlm_direct_printed_page_patterns": [
        r"<!--\s*page:\s*(\S+)\s*-->",
        r"页码[:：]\s*(SC\s+\d+)",
    ]
}

# 验证
converter = VlmDirectAsyncConverter(config)
assert converter.printed_page_extractor is not None
assert converter.printed_page_extractor.patterns == config["vlm_direct_printed_page_patterns"]
```

### 测试 2: 验证自动生成格式

```python
# 测试配置
config = {
    "prefix": "SC",
    "start": 1,
    "digits": 3,
    "separator": " "
}

# 验证
injector = CustomIDInjector(source_type="auto", source_data=config)
assert injector.get_custom_id(0) == "SC 001"
assert injector.get_custom_id(1) == "SC 002"
assert injector.get_custom_id(99) == "SC 100"
```

---

## 总结

### ✅ 已修复的问题

1. **正则配置传递** - VLM 输出提取的正则表达式现在可以正确传递
2. **格式化支持** - 自动生成支持 "SC 001" 格式（带空格、横线、下划线）
3. **UI 改进** - 正则表达式支持多行输入，更灵活

### 📝 修改的文件

1. [marker/converters/vlm_direct_async.py](marker/converters/vlm_direct_async.py)
   - 添加 `vlm_direct_printed_page_patterns` 参数
   - 传递自定义正则模式到 `PrintedPageExtractor`

2. [marker/formatters.py](marker/formatters.py)
   - 增强 `_generate_ids` 方法，支持分隔符

3. [marker/scripts/streamlit_app.py](marker/scripts/streamlit_app.py)
   - 添加分隔符选项（自动生成）
   - 改进正则表达式输入（多行文本框）
   - 添加配置传递

### 🎯 推荐使用方案

**对于 "SC 001" 这样的档案编号**:

✅ **推荐**: 使用自动生成模式
- 简单、可控、无需识别
- 配置: `prefix=SC, separator=空格, digits=3`

⚠️ **备选**: 使用 VLM 输出提取
- 需要修改提示词
- 需要配置正则表达式
- 适合页码格式不规则的情况

---

## 下一步

如果需要进一步优化，可以考虑：

1. **添加预设模板** - 为常见格式（档案编号、古籍卷标）提供预设正则
2. **实时预览** - 在 UI 中显示生成的编号预览
3. **批量测试** - 提供测试工具验证正则表达式效果

