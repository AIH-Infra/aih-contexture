# 页码标签格式调整 - 完成报告

## 调整内容

将页码标签的输出格式从：

```markdown
{n}
<!-- Page: X -->
------------------------------------------------
[页面内容]
```

调整为：

```markdown
{n}
------------------------------------------------
<!-- Page: X -->
[页面内容]
```

**关键变化**：分页符 `---` 现在紧接着在 `{n}` 锚点之后，然后才是 `<!-- Page: X -->` 标签。

## 修改的文件

### 1. marker/renderers/markdown.py

**位置**: 第 100-102 行

**修改前**:
```python
pagination_item = (
    "\n\n" + page_anchor + "\n" + page_tag + self.page_separator + "\n\n"
)
```

**修改后**:
```python
# 调整顺序：{n} -> 分页符 -> <!-- Page: X -->
pagination_item = (
    "\n\n" + page_anchor + "\n" + self.page_separator + "\n" + page_tag + "\n"
)
```

**影响范围**: Pipeline/Traditional 模式（使用 MarkdownRenderer）

### 2. marker/formatters.py

#### 修改 2.1: PageAnchorPlugin 构造函数

**位置**: 第 60-79 行

**修改**: 添加 `page_separator` 参数

```python
def __init__(self,
             formatter: Optional[PageAnchorFormatter] = None,
             enabled: bool = True,
             position: str = "before",
             separator: str = "\n\n",
             page_separator: str = "---",  # 新增：页面分隔符
             custom_id_injector: Optional['CustomIDInjector'] = None):
    ...
    self.page_separator = page_separator  # 新增
```

#### 修改 2.2: wrap_page_content 方法

**位置**: 第 108-118 行

**修改**: 调整锚点、分隔符和标签的顺序

```python
# 调整顺序：{n} -> 分页符 -> <!-- Page: X -->
if self.position == "before":
    return f"{anchor}{self.separator}{self.page_separator}{self.separator}{page_tag}{content}"
elif self.position == "after":
    return f"{content}{self.separator}{self.page_separator}{self.separator}{page_tag}{anchor}"
elif self.position == "both":
    return f"{anchor}{self.separator}{self.page_separator}{self.separator}{page_tag}{content}{self.separator}{self.page_separator}{self.separator}{page_tag}{anchor}"
```

**影响范围**: VLM Direct 模式（使用 PageAnchorPlugin）

### 3. marker/converters/vlm_direct_async.py

**位置**: 第 169-175 行

**修改**: 传递 `page_separator` 参数给 PageAnchorPlugin

```python
self.page_anchor_plugin = PageAnchorPlugin(
    formatter=formatter,
    enabled=enable_anchors,
    position=anchor_position,
    separator="\n\n",
    page_separator=self.page_separator.strip(),  # 新增：传递页面分隔符
    custom_id_injector=custom_id_injector
)
```

**影响范围**: VLM Direct 模式初始化

## 输出格式对比

### Pipeline/Traditional 模式

**修改前**:
```markdown
{0}
<!-- Page: 127 -->
------------------------------------------------
第一页内容...

{1}
<!-- Page: 128 -->
------------------------------------------------
第二页内容...
```

**修改后**:
```markdown
{0}
------------------------------------------------
<!-- Page: 127 -->
第一页内容...

{1}
------------------------------------------------
<!-- Page: 128 -->
第二页内容...
```

### VLM Direct 模式

**修改前**:
```markdown
{0}

<!-- Page: 127 -->
第一页内容...

---

{1}

<!-- Page: 128 -->
第二页内容...
```

**修改后**:
```markdown
{0}

---

<!-- Page: 127 -->
第一页内容...

---

{1}

---

<!-- Page: 128 -->
第二页内容...
```

## 设计理念

### 1. 统一的层次结构

```
{n}                    ← 定位锚点（机器页码）
---                    ← 视觉分隔符
<!-- Page: X -->       ← 显示标签（印刷页码/自定义编号）
[页面内容]             ← 实际内容
```

### 2. 优势

1. **视觉清晰**: 分隔符紧跟锚点，形成明确的页面边界
2. **逻辑一致**: 所有模式使用相同的顺序
3. **易于解析**: 固定的结构便于程序化处理
4. **向后兼容**: 不影响现有的锚点提取逻辑

### 3. 语义说明

- `{n}`: 机器页码，用于程序定位和区间提取
- `---`: 视觉分隔符，标记页面边界
- `<!-- Page: X -->`: 人类可读的页码标签，显示印刷页码或自定义编号

## 测试验证

### 测试脚本

可以使用以下脚本验证格式：

```bash
# Pipeline 模式
python verify_page_tags.py <pdf_path>

# VLM Direct 模式
python vlm_direct_convert.py <pdf_path>
```

### 预期输出

所有模式都应该输出：

```markdown
{n}
---
<!-- Page: X -->
[内容]
```

## 兼容性说明

### 向后兼容

- ✅ 锚点格式 `{n}` 保持不变
- ✅ 页码标签格式 `<!-- Page: X -->` 保持不变
- ✅ 只是调整了顺序，不影响现有解析逻辑

### 影响范围

- ✅ Pipeline/Traditional 模式：已更新
- ✅ VLM Direct 模式：已更新
- ✅ 所有转换模式统一格式

## 总结

此次调整确保了所有转换模式（Pipeline、VLM Direct）使用统一的页码标签格式，分页符紧接着在锚点之后，然后是页码标签，最后是页面内容。这提供了更清晰的视觉层次和更一致的输出格式。

**修改完成时间**: 2026-02-02
**影响的转换模式**: 所有模式（Pipeline、VLM Direct）
**向后兼容性**: 完全兼容
