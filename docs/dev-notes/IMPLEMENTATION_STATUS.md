# Chandra OCR Direct 实施总结

## ✅ 已完成的修改

### 1. 更新 Prompt
**文件**: `marker/services/ocr_chandra.py`
**状态**: ✅ 完成

- 使用官方 `OCR_LAYOUT_PROMPT`
- Chandra 输出 HTML（data-bbox + data-label）
- 坐标归一化到 0-1024

### 2. 简化响应解析
**文件**: `marker/services/ocr_chandra.py`
**状态**: ✅ 完成

- `_parse_response()` 直接返回 HTML 字符串
- 不再尝试解析 JSON

---

## 🔄 待完成的修改

### 3. 添加 HTML 解析方法
**文件**: `marker/builders/ocr_parser.py`
**需要添加**: `parse_chandra_html_to_page()` 方法

**核心功能**:
- 使用 BeautifulSoup 解析 HTML
- 提取 data-bbox 和 data-label
- 转换坐标（0-1024 → 像素）
- 创建 Block 对象
- 返回 PageGroup

### 4. 更新 Converter 调用
**文件**: `marker/converters/ocr_direct_async.py`
**需要修改**: 调用新的解析方法

### 5. 创建多格式渲染器
**新文件**: `marker/renderers/multi_format.py`
**功能**: 同时输出 JSON、HTML、Markdown

### 6. 更新 Streamlit UI
**文件**: `marker/scripts/streamlit_app.py`
**功能**: 添加格式选择（多选框）

---

## 📝 下一步行动

由于输出限制，我建议：

**方案 A**: 我逐个文件修改，每次只修改一个方法
**方案 B**: 我创建完整的代码片段，你手动复制粘贴
**方案 C**: 我创建新文件，包含所有修改

**你希望采用哪种方案？**

或者，我可以先完成最关键的部分（HTML 解析器），然后测试是否能正常工作？
