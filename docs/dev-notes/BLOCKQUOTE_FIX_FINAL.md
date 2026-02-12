# Blockquote 处理器修复完成（更新版）

## 修改总结

### 问题描述

**原始问题**：
- 使用 **Pipeline 模式 + Surya Layout**（无 LLM）
- 诗歌块（居中/缩进）没有被标记为 blockquote
- 诗歌后的正常段落被错误标记为 blockquote（显示为 `>`）

**根本原因**：
1. BlockquoteProcessor 的延续逻辑过于宽松
2. 当诗歌被标记为 blockquote 后，下一段只要对齐就会延续标记
3. 没有检查下一段是否"回退"到左侧（outdent）

---

## 修改内容

### 1. 修复 BlockquoteProcessor 延续逻辑

**文件**: [marker/processors/blockquote.py](marker/processors/blockquote.py#L53-L68)

**修改**：
```python
# 添加 x_not_outdent 检查（Line 58）
x_not_outdent = block.polygon.x_start >= prev_block.polygon.x_start - (self.x_start_tolerance * prev_block.polygon.width)

# 修改延续条件（Line 60）
if matching_x_end and matching_x_start and y_indent and x_not_outdent:
    block.blockquote = True
```

**效果**：
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
- BlockquoteProcessor 可以通过配置启用/禁用
- 默认值：`True`（保持向后兼容）

---

### 3. 在 Streamlit UI 添加配置选项（正确位置）

**文件**: [marker/scripts/streamlit_app.py](marker/scripts/streamlit_app.py)

#### ✅ 修改 1: 在主配置区域添加 blockquote 配置（Line 626-636）

**位置**: 在"印刷页码提取"配置之后，"自定义编号配置"之前

```python
# 🆕 基础处理器配置
st.markdown("---")
st.caption("🔧 基础处理器配置")

blockquote_enabled = st.checkbox(
    "引用块检测",
    value=True,
    help="检测并标记缩进的引用块（使用 > 符号）。如果文档中有诗歌或特殊缩进格式，建议禁用此选项。",
    key="blockquote_enabled_main"
)
```

**重要**：
- ✅ 在主配置区域，所有模式都可见
- ✅ 不依赖 LLM 配置
- ✅ 适用于 Pipeline 模式 + Surya Layout

#### ✅ 修改 2: 配置传递（Line 104）

```python
"blockquote_enabled": bool(config_params.get("blockquote_enabled", True)),
```

#### ✅ 修改 3: 配置传递到 config_params（Line 2298-2301）

```python
# 🆕 基础处理器配置（所有模式通用，从主配置区域获取）
config_params.update({
    "blockquote_enabled": blockquote_enabled,
})
```

**重要**：
- ✅ 独立于 LLM 配置
- ✅ 所有模式通用

---

## 使用指南

### 场景 1: Pipeline 模式 + Surya Layout（你的情况）

**配置步骤**：
1. 选择 "Pipeline (传统模式)"
2. 向下滚动到 "🔧 基础处理器配置"
3. 根据需要勾选/取消 "引用块检测"

**建议**：
- **文档包含诗歌**：取消勾选（禁用 blockquote）
- **文档包含引用**：保持勾选（启用 blockquote）

---

### 场景 2: VLM Direct 模式

**配置步骤**：
1. 选择 "VLM Direct"
2. 向下滚动到 "🔧 基础处理器配置"
3. 根据需要勾选/取消 "引用块检测"

**说明**：
- VLM Direct 模式也可以使用 blockquote 检测
- 配置位置相同

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

## 修改文件列表

1. ✅ [marker/processors/blockquote.py](marker/processors/blockquote.py)
   - 修复延续逻辑，添加 `x_not_outdent` 检查

2. ✅ [marker/converters/pdf.py](marker/converters/pdf.py)
   - 添加 BlockquoteProcessor 到可配置列表

3. ✅ [marker/scripts/streamlit_app.py](marker/scripts/streamlit_app.py)
   - 在主配置区域添加 blockquote 配置（Line 626-636）
   - 配置传递（Line 104）
   - 配置传递到 config_params（Line 2298-2301）
   - **删除了 LLM 配置区域中的重复配置**

---

## 关键改进

### ✅ 修复前的问题
- blockquote 配置在 LLM 配置区域内
- Pipeline 模式 + Surya Layout 无法访问配置
- 必须启用 LLM 才能配置 blockquote

### ✅ 修复后的改进
- blockquote 配置在主配置区域
- 所有模式都可以访问
- 不依赖 LLM 配置
- 适用于 Pipeline 模式 + Surya Layout

---

## 测试验证

### 测试 1: Pipeline 模式 + Surya Layout

**步骤**：
1. 选择 "Pipeline (传统模式)"
2. 不启用 LLM
3. 找到 "🔧 基础处理器配置"
4. 取消勾选 "引用块检测"
5. 上传包含诗歌的文档
6. 运行转换

**预期结果**：
- ✅ 诗歌保持原始格式
- ✅ 不会被标记为 `>`
- ✅ 诗歌后的段落也不会被标记

---

### 测试 2: 启用 blockquote 检测

**步骤**：
1. 选择 "Pipeline (传统模式)"
2. 保持勾选 "引用块检测"
3. 上传包含引用的文档
4. 运行转换

**预期结果**：
- ✅ 缩进的引用块被标记为 `>`
- ✅ 引用后的正常段落不会被误标记

---

## 完成状态

✅ BlockquoteProcessor 延续逻辑已修复
✅ 可配置性已添加
✅ Streamlit UI 已更新（正确位置）
✅ 配置独立于 LLM
✅ 适用于 Pipeline 模式 + Surya Layout
✅ 向后兼容

**现在可以测试了！**
