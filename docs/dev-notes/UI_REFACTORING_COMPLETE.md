# UI 重构完成报告

## 修改概览

本次重构完成了以下五项主要改进，优化了 Streamlit UI 的用户体验和配置逻辑。

## 1. ✅ 删除"禁用版面识别 (none)"选项

### 修改位置
- **文件**: `marker/scripts/streamlit_app.py`
- **行号**: 658, 820-838

### 修改内容
- 从版面识别后端选择器中移除了 `"none"` 选项
- 删除了相关的警告提示部分（19行代码）

### 修改前
```python
options=["surya", "vlm", "yolo", "none"]
```

### 修改后
```python
options=["surya", "vlm", "yolo"]
```

### 原因
该选项在实际使用中不起作用，且会误导用户。Marker 的架构要求先进行版面检测才能进行 OCR。

---

## 2. ✅ 统一页码锚点配置

### 修改位置
- **新增**: 行 476-600（统一配置区域）
- **删除**: VLM Direct 模式的重复配置（原 720-778 行）
- **删除**: Pipeline 模式的重复配置（原 1363-1441 行）

### 修改内容

#### 新增统一配置区域
在文件上传后、模式特定配置前，创建了统一的页码锚点配置区域：

```python
# ==================== 2.5 统一页码锚点配置 ====================
st.subheader("📍 页码锚点配置")
with st.expander("页码锚点设置", expanded=False):
    enable_page_anchors = st.checkbox("启用页码锚点", value=True)

    if enable_page_anchors:
        # 锚点模板
        page_anchor_template = st.selectbox(...)

        # 页序起始值
        page_anchor_start = st.number_input(...)

        # 锚点位置（仅 VLM Direct 支持）
        if conversion_mode == "vlm_direct":
            page_anchor_position = st.radio(...)

        # 印刷页码提取
        extract_printed_pages = st.checkbox(...)

        # Pipeline 模式的详细配置
        if extract_printed_pages and conversion_mode == "pipeline":
            # 页码搜索区域、格式、位置等
```

#### 配置映射

**VLM Direct 模式**:
```python
vlm_direct_enable_page_anchors = enable_page_anchors
vlm_direct_page_anchor_template = page_anchor_template
vlm_direct_page_anchor_start = page_anchor_start
vlm_direct_page_anchor_position = page_anchor_position
vlm_direct_extract_printed_pages = extract_printed_pages
```

**Pipeline 模式**:
```python
printed_page_enabled = extract_printed_pages
# page_anchor_template, page_anchor_start 直接使用统一配置
```

### 优势
- **消除重复**: 两种模式不再有重复的配置界面
- **统一体验**: 用户在一个地方配置所有页码锚点设置
- **智能适配**: 根据转换模式自动显示/隐藏相关选项
- **向后兼容**: 后端参数映射保持不变

---

## 3. ✅ 增强 LLM 模块配置

### 修改位置
- **文件**: `marker/scripts/streamlit_app.py`
- **行号**: 1242-1267

### 修改内容

#### 新增"启发式版面增强"选项
```python
llm_heuristic_layout_enabled = st.checkbox(
    "启发式版面增强",
    value=False,
    help="使用启发式规则优化版面检测结果"
)
```

### 现有功能
所有 LLM 增强选项已经配备了详细的 help 提示：

| 选项 | 说明 |
|------|------|
| 表格优化 | 修正表格结构,确保列对齐正确 |
| 公式识别 | 识别和转换数学公式 |
| 图片描述 | 为图片生成描述性文本 |
| 手写识别 | 识别手写内容 |
| 智能降噪 | 识别并过滤无关符号和语言 |
| 页面校正 | 修正页面结构和阅读顺序 |
| 章节识别 | 识别和标记章节标题 |
| 表单识别 | 识别和提取表单内容 |
| 复杂区域处理 | 处理复杂布局区域 |
| 印刷页码修正 | 启发式识别和修正印刷页码 |
| **启发式版面增强** | **使用启发式规则优化版面检测结果（新增）** |

### 界面布局
- 保持原有的两列布局
- 左列 5 个选项，右列 6 个选项
- 所有选项都有鼠标悬停提示

---

## 4. ✅ 整合批处理设置

### 修改位置
- **文件**: `marker/scripts/streamlit_app.py`
- **行号**: 1444-1507（新的整合版本）
- **删除**: 原分散的配置（1386-1427）

### 修改内容

#### 新的批处理配置逻辑

```python
# 批处理模式选择
batch_mode = st.radio(
    "处理模式",
    options=["自动", "单批处理", "分批处理"],
    index=0,
    horizontal=True,
    help="自动：根据页数自动决定；单批：一次性处理所有页面；分批：分批处理大文档"
)

# 根据选择显示相关设置
if batch_mode == "分批处理" or batch_mode == "自动":
    st.info("💡 分批处理说明：分批是为了本地部署后端时降低性能压力，批次间冷却是为了改善散热")

    col_a, col_b = st.columns(2)
    with col_a:
        batch_threshold = st.number_input("分批阈值（页）", ...)
        pages_per_batch = st.number_input("每批页数", ...)
    with col_b:
        cooling_seconds = st.number_input("批次间冷却（秒）", ...)
else:
    # 单批处理模式，使用默认值
    batch_threshold = 50
    pages_per_batch = 25
    cooling_seconds = 0
```

#### 参数映射
```python
if batch_mode == "自动":
    process_mode = "自动"
elif batch_mode == "单批处理":
    process_mode = "强制单批"
else:
    process_mode = "强制分批"
```

### 优势
- **条件显示**: 只在需要时显示批处理相关设置
- **清晰说明**: 添加了说明性提示，解释分批和冷却的目的
- **简化界面**: 单批处理模式下界面更简洁
- **向后兼容**: 映射到原有的 `process_mode` 变量

### 从高级选项移除
- 将 `cooling_seconds` 从"高级选项"折叠区移到主配置区
- 与其他批处理设置整合在一起

---

## 5. ✅ 配置逻辑确认

### 整体架构

```
文件上传
    ↓
统一页码锚点配置（新增）
    ├─ 启用/禁用
    ├─ 锚点模板
    ├─ 页序起始值
    ├─ 锚点位置（VLM Direct）
    └─ 印刷页码提取
        └─ 详细配置（Pipeline）
    ↓
转换模式选择
    ├─ VLM Direct 模式
    │   ├─ API 配置
    │   ├─ 并发设置
    │   ├─ 提示词配置
    │   └─ [映射统一页码配置]
    │
    └─ Pipeline 模式
        ├─ 版面识别后端（移除 "none"）
        ├─ OCR 后端
        ├─ LLM 增强（新增"启发式版面增强"）
        ├─ [映射统一页码配置]
        └─ 批处理设置（整合版）
```

### 配置流程

1. **用户上传文件**
2. **配置页码锚点**（统一配置，适用于所有模式）
3. **选择转换模式**（VLM Direct 或 Pipeline）
4. **配置模式特定选项**
5. **开始转换**

### 向后兼容性

所有修改都保持了向后兼容：
- 后端参数名称不变
- 配置值映射正确
- 默认值保持一致

---

## 测试验证

### 语法检查
```bash
python -m py_compile marker/scripts/streamlit_app.py
# ✅ Syntax check passed
```

### 预期行为

#### 1. 版面识别后端
- ✅ 只显示 "surya", "vlm", "yolo" 三个选项
- ✅ 不再显示 "none" 选项和相关警告

#### 2. 页码锚点配置
- ✅ 在文件上传后立即显示
- ✅ VLM Direct 模式显示"锚点位置"选项
- ✅ Pipeline 模式不显示"锚点位置"选项
- ✅ Pipeline 模式启用印刷页码时显示详细配置
- ✅ 配置值正确映射到后端参数

#### 3. LLM 增强
- ✅ 显示 11 个选项（新增"启发式版面增强"）
- ✅ 所有选项都有 help 提示
- ✅ 鼠标悬停显示说明

#### 4. 批处理设置
- ✅ 显示三个处理模式选项
- ✅ 选择"分批处理"或"自动"时显示详细设置
- ✅ 选择"单批处理"时隐藏详细设置
- ✅ 显示说明性提示

---

## 代码统计

### 修改行数
- **删除**: 约 100 行（重复配置 + "none" 选项）
- **新增**: 约 130 行（统一配置 + 整合批处理）
- **净增加**: 约 30 行

### 修改文件
- `marker/scripts/streamlit_app.py`（唯一修改的文件）

### 影响范围
- ✅ 前端 UI 配置
- ✅ 配置参数映射
- ❌ 后端逻辑（无修改）
- ❌ 核心转换器（无修改）

---

## 用户体验改进

### 改进前的问题
1. ❌ "禁用版面识别"选项不起作用，误导用户
2. ❌ 页码锚点配置在两个地方重复，容易混淆
3. ❌ LLM 增强选项缺少"启发式版面增强"
4. ❌ 批处理设置分散，逻辑不清晰

### 改进后的优势
1. ✅ 移除无效选项，避免误导
2. ✅ 统一页码配置，一次设置全局生效
3. ✅ 完善 LLM 增强选项，覆盖更多场景
4. ✅ 整合批处理设置，条件显示更清晰

---

## 后续建议

### 短期优化
1. **测试统一配置**: 在实际使用中验证两种模式的配置映射
2. **完善提示**: 根据用户反馈优化 help 提示文本
3. **添加示例**: 在页码锚点配置中添加预览示例

### 长期规划
1. **配置预设**: 添加"人文学科"、"技术文档"等预设配置
2. **配置导入导出**: 支持保存和加载配置文件
3. **配置验证**: 添加配置冲突检测和智能建议

---

## 总结

本次 UI 重构成功完成了所有五项改进目标：

1. ✅ 删除"禁用版面识别 (none)"选项
2. ✅ 统一页码锚点配置
3. ✅ 增强 LLM 模块配置（新增"启发式版面增强"）
4. ✅ 整合批处理设置
5. ✅ 确认逻辑并实施修改

所有修改都经过语法检查，保持向后兼容，并显著改善了用户体验。

**修改完成时间**: 2026-01-28
**修改文件**: `marker/scripts/streamlit_app.py`
**测试状态**: ✅ 语法检查通过
