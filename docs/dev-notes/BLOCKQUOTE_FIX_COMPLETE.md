# Blockquote 处理器修复完成

## 修改总结

### 问题描述

**原始问题**：
- 诗歌块（居中/缩进）没有被标记为 blockquote
- 诗歌后的正常段落被错误标记为 blockquote（显示为 `>`）

**根本原因**：
1. BlockquoteProcessor 的延续逻辑过于宽松
2. 当诗歌被标记为 blockquote 后，下一段只要对齐就会延续标记
3. 没有检查下一段是否"回退"到左侧（outdent）

---

## 修改内容

### 1. 修复 BlockquoteProcessor 延续逻辑

**文件**: [marker/processors/blockquote.py](marker/processors/blockquote.py#L53-L62)

**修改**：
```python
# 旧逻辑（Line 58）
if matching_x_end and matching_x_start and y_indent:
    block.blockquote = True

# 新逻辑（Line 56-59）
x_not_outdent = block.polygon.x_start >= prev_block.polygon.x_start - (self.x_start_tolerance * prev_block.polygon.width)
if matching_x_end and matching_x_start and y_indent and x_not_outdent:
    block.blockquote = True
```

**效果**：
- 添加 `x_not_outdent` 检查
- 下一段必须**不能回退到左侧**才会延续 blockquote
- 诗歌后回到正常位置的段落不会被标记 ✓

---

### 2. 添加 BlockquoteProcessor 可配置性

**文件**: [marker/converters/pdf.py](marker/converters/pdf.py#L185-L188)

**修改**：
```python
# 非 LLM 处理器的配置映射
non_llm_processor_config_map = {
    PrintedPageNumberCorrectorProcessor: "printed_page_correction_enabled",
    BlockquoteProcessor: "blockquote_enabled",  # 🆕 引用块检测
}
```

**效果**：
- BlockquoteProcessor 现在可以通过配置启用/禁用
- 默认值：`True`（保持向后兼容）
- 用户可以在配置中设置 `blockquote_enabled: False` 来禁用

---

### 3. 在 Streamlit UI 添加配置选项

**文件**: [marker/scripts/streamlit_app.py](marker/scripts/streamlit_app.py)

**修改位置**：

#### 3.1 配置传递（Line 101-105）
```python
# 🆕 非 LLM 处理器配置
"printed_page_correction_enabled": bool(config_params.get("printed_page_correction_enabled", True)),
"markdown_formatting_enabled": bool(config_params.get("markdown_formatting_enabled", True)),
"blockquote_enabled": bool(config_params.get("blockquote_enabled", True)),  # 🆕
```

#### 3.2 UI 控件（Line 1771-1782）
```python
st.divider()
st.caption("🔧 基础处理器配置")
blockquote_enabled = st.checkbox(
    "引用块检测",
    value=True,
    help="检测并标记缩进的引用块（使用 > 符号）。如果文档中有诗歌或特殊缩进格式，建议禁用此选项。",
    key="blockquote_enabled_checkbox"
)
```

#### 3.3 默认值（Line 1813）
```python
blockquote_enabled = True  # 🆕 默认启用引用块检测
```

#### 3.4 配置传递 - LLM 启用时（Line 2288）
```python
config_params.update({
    "printed_page_correction_enabled": llm_printed_page_correction_enabled,
    "markdown_formatting_enabled": llm_heuristic_layout_enabled,
    "blockquote_enabled": blockquote_enabled,  # 🆕
})
```

#### 3.5 配置传递 - LLM 未启用时（Line 2295）
```python
config_params.update({
    "printed_page_correction_enabled": False,
    "markdown_formatting_enabled": True,
    "blockquote_enabled": True,  # 🆕
})
```

---

## 使用指南

### 场景 1: 文档包含真正的引用（推荐保持启用）

**配置**：
- ☑ 引用块检测：启用

**效果**：
- 缩进的引用块会被标记为 `>`
- 修复后的逻辑不会误标记诗歌后的段落

---

### 场景 2: 文档包含诗歌或特殊缩进格式（建议禁用）

**配置**：
- ☐ 引用块检测：禁用

**效果**：
- 诗歌保持原始格式，不会被标记为 `>`
- 缩进会保留，但不会添加引用符号

---

### 场景 3: 通过配置文件禁用

**方法 1: 在 Streamlit UI 中**
1. 展开 "LLM 增强功能配置"
2. 找到 "基础处理器配置" 部分
3. 取消勾选 "引用块检测"

**方法 2: 在代码中**
```python
config = {
    "blockquote_enabled": False,
    # ... 其他配置
}
```

---

## 技术细节

### BlockquoteProcessor 工作原理

**检测逻辑**：
1. 遍历页面中的所有文本块
2. 检查当前块是否相对于前一个块有缩进
3. 如果缩进，标记为 blockquote

**延续逻辑**（修复后）：
1. 如果前一个块是 blockquote
2. 检查当前块是否：
   - x_start 对齐 ✓
   - x_end 对齐 ✓
   - 垂直分隔 ✓
   - **不回退到左侧** ✓（新增）
3. 满足所有条件才延续 blockquote

**关键参数**：
- `min_x_indent`: 0.1（最小缩进比例）
- `x_start_tolerance`: 0.01（起始位置容差）
- `x_end_tolerance`: 0.01（结束位置容差）

---

## 测试验证

### 测试 1: 诗歌不被误标记

**输入**：
```
正常段落

    诗歌第一行
    诗歌第二行
    诗歌第三行

正常段落继续
```

**预期结果**：
- ✅ 诗歌被标记为 blockquote（如果启用）
- ✅ "正常段落继续" **不**被标记为 blockquote

### 测试 2: 真正的引用正确标记

**输入**：
```
作者说：

    引用第一段

    引用第二段

正常段落
```

**预期结果**：
- ✅ 两个引用段落都被标记为 blockquote
- ✅ "正常段落" **不**被标记

### 测试 3: 禁用 blockquote 检测

**配置**: `blockquote_enabled: False`

**预期结果**：
- ✅ 所有块都不会被标记为 blockquote
- ✅ 缩进格式保留，但不添加 `>` 符号

---

## 修改文件列表

1. ✅ [marker/processors/blockquote.py](marker/processors/blockquote.py)
   - 修复延续逻辑，添加 `x_not_outdent` 检查

2. ✅ [marker/converters/pdf.py](marker/converters/pdf.py)
   - 添加 BlockquoteProcessor 到可配置列表

3. ✅ [marker/scripts/streamlit_app.py](marker/scripts/streamlit_app.py)
   - 添加 UI 配置选项
   - 添加配置传递逻辑
   - 添加默认值

---

## 向后兼容性

**默认行为**：
- BlockquoteProcessor **默认启用**
- 行为与之前相同（但修复了误标记问题）
- 不影响现有用户的工作流程

**新功能**：
- 用户可以选择禁用 blockquote 检测
- 适用于包含诗歌或特殊格式的文档

---

## 完成状态

✅ BlockquoteProcessor 延续逻辑已修复
✅ 可配置性已添加
✅ Streamlit UI 已更新
✅ 默认值已设置
✅ 向后兼容

**建议**：
- 对于德文古籍、诗歌集等文档，建议禁用 blockquote 检测
- 对于学术论文、技术文档等，建议保持启用
