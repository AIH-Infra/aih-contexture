# Chandra OCR Direct 快速实施指南

## ✅ 已完成的修改

### 1. 更新 Prompt ✅
**文件**: `marker/services/ocr_chandra.py`
- 使用官方 `OCR_LAYOUT_PROMPT`
- Chandra 输出 HTML（data-bbox + data-label）

### 2. 简化响应解析 ✅
**文件**: `marker/services/ocr_chandra.py`
- `_parse_response()` 直接返回 HTML 字符串

### 3. 更新 parse_to_page ✅
**文件**: `marker/builders/ocr_parser.py`
- 添加了 Chandra HTML 检测逻辑

### 4. 创建 HTML 解析器代码 ✅
**文件**: `chandra_html_parser_method.py`
- 包含 `parse_chandra_html_to_page()` 方法
- 包含 `_map_chandra_label()` 方法

---

## 📝 待手动完成的步骤

### 步骤 1: 添加 HTML 解析器方法

**操作**:
1. 打开 `marker/builders/ocr_parser.py`
2. 找到 line 117 (`def parse_json_to_page`)
3. 在此之前插入 `chandra_html_parser_method.py` 中的两个方法：
   - `parse_chandra_html_to_page()`
   - `_map_chandra_label()`

**注意**: 需要在文件顶部添加导入：
```python
from bs4 import BeautifulSoup
import json
```

---

### 步骤 2: 测试基本功能

**测试命令**:
```bash
streamlit run marker/scripts/streamlit_app.py
```

**测试步骤**:
1. 选择 "OCR Direct" 模式
2. 上传一个 PDF 文件
3. 点击"开始转换"
4. 查看是否生成 Markdown 文件
5. 检查 Markdown 内容是否正确

**预期结果**:
- ✅ Chandra 返回 HTML
- ✅ 解析器成功解析
- ✅ 创建 PageGroup（children 不为 None）
- ✅ Markdown 文件包含内容

---

## 🔄 如果测试成功，继续以下步骤

### 步骤 3: 添加多格式输出（可选）

**目标**: 同时输出 JSON、HTML、Markdown

**需要修改的文件**:
1. `marker/scripts/streamlit_app.py` - 添加格式选择
2. 创建多格式渲染逻辑

**暂时可以跳过**: 先确保基本功能正常工作

---

## 🐛 故障排查

### 问题 1: ImportError (BeautifulSoup)
**解决方案**:
```bash
pip install beautifulsoup4
```

### 问题 2: page.children 仍然是 None
**检查**:
- 查看日志，确认调用了 `parse_chandra_html_to_page()`
- 检查 HTML 是否包含 `data-bbox` 和 `data-label`
- 查看是否有解析错误日志

### 问题 3: Markdown 文件为空
**检查**:
- 查看日志中 "Created PageGroup with X blocks"
- 如果 X = 0，说明没有成功解析任何 block
- 检查 bbox 解析是否失败

---

## 📊 当前架构

```
PDF → 图像 → Chandra OCR (官方 Prompt)
         ↓
    HTML (data-bbox + data-label)
         ↓
    parse_chandra_html_to_page()
         ↓
    PageGroup (children = [Block, Block, ...])
         ↓
    Document
         ↓
    MarkdownRenderer
         ↓
    Markdown 文件
```

---

## 🚀 下一步

1. **立即测试**: 添加 HTML 解析器方法后测试
2. **查看日志**: 确认解析过程正常
3. **验证输出**: 检查 Markdown 内容
4. **报告结果**: 告诉我测试结果

---

**关键文件**:
- ✅ `marker/services/ocr_chandra.py` - 已修改
- ✅ `marker/builders/ocr_parser.py` - 已部分修改
- 📝 `chandra_html_parser_method.py` - 待添加到 ocr_parser.py

**状态**: 准备测试
