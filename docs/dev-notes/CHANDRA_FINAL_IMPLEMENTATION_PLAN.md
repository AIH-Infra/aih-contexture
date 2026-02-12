# Chandra OCR Direct 最终实施方案

## 📋 方案概述

### 核心目标
1. ✅ 使用官方 `OCR_LAYOUT_PROMPT` 获取高质量 HTML 输出
2. ✅ 支持同时输出 JSON、HTML、Markdown 三种格式
3. ✅ 保持当前 API 配置不变
4. ✅ 完整的坐标和结构信息保留

### 架构设计

```
PDF 页面
    ↓
渲染为图像
    ↓
Chandra OCR (官方 Prompt)
    ↓
HTML 输出 (data-bbox + data-label)
    ↓
解析为 LayoutBlock 列表
    ↓
转换为 Marker Document
    ↓
多格式渲染器：
    ├── JSON Renderer → .json 文件
    ├── HTML Renderer → .html 文件
    └── Markdown Renderer → .md 文件
```

---

## 🔧 实施步骤

### 步骤 1: 更新 Prompt (保持 API 不变)

**文件**: `marker/services/ocr_chandra.py`

**目标**: 使用官方 OCR_LAYOUT_PROMPT，但保持当前 API 调用方式

**修改点**:
- ✅ 更新 `_build_prompt()` 方法
- ✅ 保持 API 端点和参数不变
- ✅ 只修改 prompt 内容

---

### 步骤 2: 创建 HTML 解析器

**文件**: `marker/builders/ocr_parser.py`

**目标**: 解析 Chandra 的 HTML 输出为 Marker Block 对象

**新增方法**:
- `parse_chandra_html_to_page()` - 主解析方法
- `_map_chandra_label_to_block_type()` - 标签映射
- `_convert_bbox_to_pixels()` - 坐标转换

---

### 步骤 3: 创建多格式输出系统

**新文件**: `marker/renderers/multi_format.py`

**目标**: 统一管理多格式输出

**功能**:
- 接收 Document 对象
- 根据配置输出多种格式
- 保存到指定目录

---

### 步骤 4: 更新 Converter

**文件**: `marker/converters/ocr_direct_async.py`

**目标**: 调用新的解析器和渲染器

**修改点**:
- 使用 `parse_chandra_html_to_page()` 解析 HTML
- 传递 `bbox_scale=1024` 参数
- 返回完整的 Document 对象

---

### 步骤 5: 更新 Streamlit UI

**文件**: `marker/scripts/streamlit_app.py`

**目标**: 支持多格式输出选择

**新增配置**:
- 输出格式选择（多选框）
- 默认全选（JSON + HTML + Markdown）

---

## 📝 详细代码修改

### 修改 1: 更新 Prompt

**文件**: `marker/services/ocr_chandra.py`

**位置**: `_build_prompt()` 方法

**修改内容**: 使用官方完整 Prompt

---

### 修改 2: 创建 HTML 解析器

**文件**: `marker/builders/ocr_parser.py`

**新增方法**: `parse_chandra_html_to_page()`

**核心逻辑**:
1. 使用 BeautifulSoup 解析 HTML
2. 提取所有顶层 `<div>` 元素
3. 读取 `data-bbox` 和 `data-label` 属性
4. 转换坐标（0-1024 → 实际像素）
5. 映射标签（Chandra → Marker）
6. 创建 Block 对象
7. 返回 PageGroup

---

### 修改 3: 创建多格式渲染器

**新文件**: `marker/renderers/multi_format.py`

**类**: `MultiFormatRenderer`

**方法**:
- `render_json()` - 输出 JSON
- `render_html()` - 输出 HTML
- `render_markdown()` - 输出 Markdown
- `render_all()` - 输出所有格式

---

### 修改 4: 更新 Converter

**文件**: `marker/converters/ocr_direct_async.py`

**修改位置**: `_process_page()` 方法

**修改内容**:
```python
# 4. 解析输出 (使用新的 HTML 解析器)
page = self.parser.parse_chandra_html_to_page(
    ocr_output,  # HTML 字符串
    page_num,
    img_size,
    bbox_scale=1024
)
```

---

### 修改 5: 更新 Streamlit UI

**文件**: `marker/scripts/streamlit_app.py`

**新增配置**:
```python
# 输出格式选择
output_formats = st.multiselect(
    "输出格式",
    options=["Markdown", "JSON", "HTML"],
    default=["Markdown", "JSON", "HTML"],
    help="选择要输出的格式（可多选）"
)
```

**修改输出逻辑**:
```python
# 根据选择输出多种格式
from marker.renderers.multi_format import MultiFormatRenderer

multi_renderer = MultiFormatRenderer()
output_files = multi_renderer.render_all(
    document,
    output_dir=st.session_state.output_dir,
    filename_base=fname_base,
    formats=output_formats
)
```

---

## 🔍 深入反思

### 反思 1: 为什么之前失败？

**问题根源**:
1. ❌ 要求 Chandra 输出 JSON → Chandra 是 OCR 模型，不是 LLM
2. ❌ 使用简化 prompt → 没有利用 Chandra 的完整能力
3. ❌ 期望完美的结构化输出 → OCR 模型不擅长生成复杂 JSON

**正确认知**:
- ✅ Chandra 是专业 OCR 模型，擅长识别文字和布局
- ✅ Chandra 的原生输出是 HTML（带坐标和标签）
- ✅ 应该使用官方 Prompt 获取最佳效果
- ✅ 后处理应该由我们的代码完成（解析 HTML → 多格式输出）

---

### 反思 2: 当前方案的优势

**技术优势**:
1. ✅ 使用官方 Prompt → 输出质量有保证
2. ✅ HTML 解析 → 比 JSON 解析更可靠
3. ✅ 保留完整信息 → 坐标、标签、内容都保留
4. ✅ 灵活的输出 → 可以生成任意格式

**用户体验**:
1. ✅ 多格式输出 → 满足不同需求
2. ✅ 可选择格式 → 灵活配置
3. ✅ 保持 API 不变 → 无需重新配置

---

### 反思 3: 潜在问题和解决方案

**问题 1**: HTML 解析可能失败
**解决方案**:
- 添加详细的错误日志
- 对每个 block 单独 try-catch
- 提供默认值（整页 bbox）

**问题 2**: 坐标转换可能不准确
**解决方案**:
- 使用官方推荐的转换公式
- 验证坐标范围（0 ≤ x ≤ width）
- 记录转换前后的坐标

**问题 3**: 标签映射可能不完整
**解决方案**:
- 提供完整的映射表（15 种 Chandra 标签）
- 默认映射到 "text"
- 记录未知标签

**问题 4**: 多格式输出可能失败
**解决方案**:
- 每种格式独立 try-catch
- 部分成功也返回结果
- 记录失败的格式

---

### 反思 4: 性能优化

**当前瓶颈**:
1. Chandra OCR 处理时间（~25-30秒/页）
2. HTML 解析时间（可忽略）
3. 多格式渲染时间（可忽略）

**优化策略**:
1. ✅ 异步并发处理（已实现）
2. ✅ 批处理 + 休息间隔（已实现）
3. ✅ 图像预处理优化（JPEG, 1024px）
4. 🆕 缓存 OCR 结果（避免重复处理）
5. 🆕 增量处理（只处理新页面）

---

### 反思 5: 与 Marker 生态的集成

**集成点**:
1. ✅ Block 对象 → 使用 Marker 的标准 Block
2. ✅ PageGroup → 使用 Marker 的 PageGroup
3. ✅ Document → 使用 Marker 的 Document
4. ✅ Renderer → 使用 Marker 的 Renderer 系统

**扩展性**:
1. ✅ 可以添加 Processor（页眉页脚过滤、脚注处理等）
2. ✅ 可以集成页码锚点系统
3. ✅ 可以使用 LLM 增强（表格、公式优化）
4. ✅ 可以导出为其他格式（PDF、DOCX等）

---

## ✅ 最终方案确认

### 核心决策

1. **Prompt**: 使用官方 `OCR_LAYOUT_PROMPT`
2. **输出**: Chandra 返回 HTML（data-bbox + data-label）
3. **解析**: BeautifulSoup 解析 HTML
4. **转换**: 坐标转换（0-1024 → 像素）+ 标签映射
5. **渲染**: 多格式渲染器（JSON + HTML + Markdown）
6. **API**: 保持当前配置不变

### 实施顺序

1. ✅ 更新 Prompt（`ocr_chandra.py`）
2. ✅ 创建 HTML 解析器（`ocr_parser.py`）
3. ✅ 创建多格式渲染器（`multi_format.py`）
4. ✅ 更新 Converter（`ocr_direct_async.py`）
5. ✅ 更新 Streamlit UI（`streamlit_app.py`）
6. ✅ 测试验证

---

## 🚀 准备开始实施

**确认要点**:
- ✅ 使用官方 Prompt
- ✅ 保持 API 配置不变
- ✅ 支持多格式输出
- ✅ 完整的错误处理
- ✅ 详细的日志记录

**下一步**: 开始逐步实施代码修改

---

**版本**: 2.0 (最终方案)
**日期**: 2026-02-05
**状态**: 待实施
