# Pipeline 模式可插拔处理器系统 - 完成报告

## 修改总结

### 问题描述

**原始问题**：
1. 禁用引用块检测后，诗歌后的段落仍然被标记为 `>`
2. blockquote 配置位置不合理（在页码锚点设置中）
3. 需要将 Pipeline 模式下的所有处理器做成可插拔的

**解决方案**：
- 创建完整的可插拔处理器系统
- 将所有基础处理器添加到配置映射
- 在 UI 中创建专门的"基础处理器配置"区域

---

## 修改内容

### 1. 扩展处理器配置映射

**文件**: [marker/converters/pdf.py](marker/converters/pdf.py#L185-L195)

**修改**：
```python
# 非 LLM 处理器的配置映射
non_llm_processor_config_map = {
    PrintedPageNumberCorrectorProcessor: "printed_page_correction_enabled",
    BlockquoteProcessor: "blockquote_enabled",  # 引用块检测
    LineMergeProcessor: "line_merge_enabled",  # 行合并
    CodeProcessor: "code_enabled",  # 代码块检测
    FootnoteProcessor: "footnote_enabled",  # 脚注检测
    ListProcessor: "list_enabled",  # 列表检测
    TableProcessor: "table_enabled",  # 表格处理
    SectionHeaderProcessor: "section_header_enabled",  # 章节标题检测
    ReferenceProcessor: "reference_enabled",  # 参考文献检测
}
```

**效果**：
- 所有基础处理器都可以通过配置启用/禁用
- 默认值：`True`（保持向后兼容）

---

### 2. 在 Streamlit UI 创建处理器配置区域

**文件**: [marker/scripts/streamlit_app.py](marker/scripts/streamlit_app.py#L626-L690)

**位置**: 在"印刷页码提取"配置之后，"自定义编号配置"之前

**修改**：
```python
# 🆕 基础处理器配置
st.markdown("---")
st.caption("🔧 基础处理器配置（Pipeline 模式）")

with st.expander("📋 文本处理器", expanded=False):
    line_merge_enabled = st.checkbox("行合并", value=True, ...)
    blockquote_enabled = st.checkbox("引用块检测", value=True, ...)
    code_enabled = st.checkbox("代码块检测", value=True, ...)

with st.expander("📚 结构处理器", expanded=False):
    section_header_enabled = st.checkbox("章节标题检测", value=True, ...)
    list_enabled = st.checkbox("列表检测", value=True, ...)
    footnote_enabled = st.checkbox("脚注检测", value=True, ...)
    reference_enabled = st.checkbox("参考文献检测", value=True, ...)

with st.expander("📊 表格处理器", expanded=False):
    table_enabled = st.checkbox("表格处理", value=True, ...)
```

**特点**：
- ✅ 使用折叠面板（expander）组织配置
- ✅ 分类清晰：文本处理器、结构处理器、表格处理器
- ✅ 所有模式通用，不依赖 LLM 配置
- ✅ 位置合理，在主配置区域

---

### 3. 配置传递

**文件**: [marker/scripts/streamlit_app.py](marker/scripts/streamlit_app.py)

#### 3.1 build_config_dict 函数（Line 101-111）
```python
# 🆕 基础处理器配置
"blockquote_enabled": bool(config_params.get("blockquote_enabled", True)),
"line_merge_enabled": bool(config_params.get("line_merge_enabled", True)),
"code_enabled": bool(config_params.get("code_enabled", True)),
"section_header_enabled": bool(config_params.get("section_header_enabled", True)),
"list_enabled": bool(config_params.get("list_enabled", True)),
"footnote_enabled": bool(config_params.get("footnote_enabled", True)),
"reference_enabled": bool(config_params.get("reference_enabled", True)),
"table_enabled": bool(config_params.get("table_enabled", True)),
```

#### 3.2 config_params 更新（Line 2349-2358）
```python
# 🆕 基础处理器配置（所有模式通用，从主配置区域获取）
config_params.update({
    "blockquote_enabled": blockquote_enabled,
    "line_merge_enabled": line_merge_enabled,
    "code_enabled": code_enabled,
    "section_header_enabled": section_header_enabled,
    "list_enabled": list_enabled,
    "footnote_enabled": footnote_enabled,
    "reference_enabled": reference_enabled,
    "table_enabled": table_enabled,
})
```

---

## 使用指南

### 场景 1: 文档包含诗歌（你的情况）

**配置步骤**：
1. 选择 "Pipeline (传统模式)"
2. 向下滚动到 "🔧 基础处理器配置（Pipeline 模式）"
3. 展开 "📋 文本处理器"
4. **取消勾选 "行合并"**（最重要！）
5. **取消勾选 "引用块检测"**

**原因**：
- **行合并**：会将诗歌的多行合并成一行
- **引用块检测**：会将诗歌标记为 `>`

**效果**：
- ✅ 诗歌保持原始分行格式
- ✅ 诗歌不会被标记为引用块
- ✅ 诗歌后的段落也不会被误标记

---

### 场景 2: 文档包含代码

**配置步骤**：
1. 展开 "📋 文本处理器"
2. 保持勾选 "代码块检测"

---

### 场景 3: 简化输出（只保留纯文本）

**配置步骤**：
1. 展开所有处理器分类
2. 取消勾选不需要的处理器：
   - 章节标题检测
   - 列表检测
   - 脚注检测
   - 参考文献检测
   - 表格处理

**效果**：
- 输出更简洁
- 只保留纯文本内容

---

## 可插拔处理器列表

### 📋 文本处理器
| 处理器 | 配置键 | 默认值 | 说明 |
|--------|--------|--------|------|
| 行合并 | `line_merge_enabled` | True | 将同一段落的多行合并 |
| 引用块检测 | `blockquote_enabled` | True | 检测缩进的引用块（`>`） |
| 代码块检测 | `code_enabled` | True | 检测代码块（` ``` `） |

### 📚 结构处理器
| 处理器 | 配置键 | 默认值 | 说明 |
|--------|--------|--------|------|
| 章节标题检测 | `section_header_enabled` | True | 检测章节标题（`#`） |
| 列表检测 | `list_enabled` | True | 检测列表项（`-` 或数字） |
| 脚注检测 | `footnote_enabled` | True | 检测脚注 |
| 参考文献检测 | `reference_enabled` | True | 检测参考文献 |

### 📊 表格处理器
| 处理器 | 配置键 | 默认值 | 说明 |
|--------|--------|--------|------|
| 表格处理 | `table_enabled` | True | 处理表格内容 |

---

## 修改文件列表

1. ✅ [marker/converters/pdf.py](marker/converters/pdf.py)
   - 扩展 `non_llm_processor_config_map`
   - 添加 9 个基础处理器的配置映射

2. ✅ [marker/scripts/streamlit_app.py](marker/scripts/streamlit_app.py)
   - 创建"基础处理器配置"区域（Line 626-690）
   - 添加配置传递（Line 101-111）
   - 添加 config_params 更新（Line 2349-2358）

---

## 测试验证

### 测试 1: 禁用行合并和引用块检测

**步骤**：
1. 重启 Streamlit 应用
2. 选择 "Pipeline (传统模式)"
3. 找到 "🔧 基础处理器配置（Pipeline 模式）"
4. 展开 "📋 文本处理器"
5. 取消勾选 "行合并" 和 "引用块检测"
6. 上传包含诗歌的文档
7. 运行转换

**预期结果**：
- ✅ 诗歌保持原始分行格式
- ✅ 诗歌不会被标记为 `>`
- ✅ 诗歌后的段落也不会被误标记

---

## 完成状态

✅ 可插拔处理器系统已创建
✅ 9 个基础处理器已添加到配置映射
✅ Streamlit UI 已更新（专门的配置区域）
✅ 配置传递逻辑已完成
✅ 向后兼容（默认全部启用）

**现在需要重启 Streamlit 应用才能看到新的配置选项！**
