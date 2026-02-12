# 修复完成 - 最终总结

## 修复日期
2026-02-01

## 问题概述

用户在使用 **Surya + 禁用 OCR + 启用印刷页码** 配置时遇到两个错误：

1. ❌ `NameError: name 'printed_page_header_y_frac' is not defined`
2. ❌ 页码锚点显示为 `{{0}}` 而不是 `{0}`

## 修复结果

✅ **所有问题已解决**

### 测试验证

```
[OK] 页码锚点格式正确: {0}, {1}, {2}...
[OK] 变量名映射正确
[OK] 无双层括号问题
[OK] 文档末尾锚点正常
```

## 修复详情

### 修复 1: 变量名映射错误

**文件**: [marker/scripts/streamlit_app.py](marker/scripts/streamlit_app.py:2028-2029)

**问题**: UI 变量名与后端参数名不匹配

**解决方案**:
```python
# 修改前（错误）
"printed_page_header_y_frac": printed_page_header_y_frac,  # ❌ 变量不存在

# 修改后（正确）
"printed_page_header_y_frac": printed_page_header_end,     # ✅ 使用 UI 变量
```

**映射关系**:
- `printed_page_header_end` (UI) → `printed_page_header_y_frac` (后端)
- `printed_page_footer_start` (UI) → `printed_page_footer_y_frac` (后端)

### 修复 2: 双层括号错误

**文件**: [marker/renderers/markdown.py](marker/renderers/markdown.py:100-102)

**问题**: PageAnchorFormatter 已包含括号，convert_div 又添加了一层

**解决方案**:
```python
# 修改前（错误）
pagination_item = "\n\n" + "{" + page_anchor + "}" + "\n" + ...
# 结果: "{" + "{0}" + "}" = "{{0}}"

# 修改后（正确）
pagination_item = "\n\n" + page_anchor + "\n" + ...
# 结果: "{0}"
```

## 现在可以使用的配置

### 配置 1: Surya + 禁用 OCR + PDF 文本层

```python
{
    "layout_backend": "surya",
    "ocr_engine": "none",
    "use_pdf_text": True,  # 使用 PDF 内嵌文本
    "use_printed_page_number": True,
}
```

**适用场景**: 电子 PDF（有文本层）

**输出示例**:
```markdown
{0}

<!-- Page: XII -->
前言内容...

{1}

<!-- Page: 1 -->
第一章内容...
```

### 配置 2: Surya + 禁用 OCR + 关闭印刷页码

```python
{
    "layout_backend": "surya",
    "ocr_engine": "none",
    "use_printed_page_number": False,
}
```

**适用场景**: 不需要页码识别

**输出示例**:
```markdown
{0}

页面内容...

{1}

页面内容...
```

### 配置 3: Surya + Surya OCR + 启用印刷页码

```python
{
    "layout_backend": "surya",
    "ocr_engine": "surya_ocr",
    "use_printed_page_number": True,
}
```

**适用场景**: 扫描件 PDF（无文本层）

**输出示例**:
```markdown
{0}

<!-- Page: 42 -->
页面内容...

{1}

<!-- Page: 43 -->
页面内容...
```

## 重要说明

### ⚠️ Surya + 禁用 OCR 的限制

**Surya 只能检测位置，不能读取文本**

如果完全禁用文本提取（`ocr_engine="none"` + `use_pdf_text=False`）：
- ❌ 无法识别印刷页码
- ❌ 无法提取文本内容
- ✅ 可以使用自定义编号（CustomIDInjector）

**解决方案**:
1. 如果 PDF 有文本层：启用 `use_pdf_text=True`
2. 如果是扫描件：启用 OCR（`ocr_engine="surya_ocr"`）
3. 如果无法识别页码：使用自定义编号

### ✅ 推荐配置

**电子 PDF**:
```python
{
    "layout_backend": "surya",
    "ocr_engine": "none",
    "use_pdf_text": True,  # 关键！
    "use_printed_page_number": True,
}
```

**扫描件 PDF**:
```python
{
    "layout_backend": "surya",
    "ocr_engine": "surya_ocr",  # 关键！
    "use_printed_page_number": True,
}
```

## 测试你的 PDF

### 快速测试

1. **检查 PDF 是否有文本层**:
   - 在 PDF 阅读器中尝试选择文本
   - 如果可以选择 → 有文本层 → 可以禁用 OCR
   - 如果不能选择 → 扫描件 → 必须启用 OCR

2. **测试配置**:
   ```python
   # 电子 PDF
   config = {
       "layout_backend": "surya",
       "ocr_engine": "none",
       "use_pdf_text": True,
       "use_printed_page_number": True,
   }

   # 扫描件 PDF
   config = {
       "layout_backend": "surya",
       "ocr_engine": "surya_ocr",
       "use_printed_page_number": True,
   }
   ```

3. **检查输出**:
   - ✅ 页码锚点应该是 `{0}`, `{1}`, `{2}`（单层括号）
   - ✅ 如果有印刷页码，应该有 `<!-- Page: X -->` 标签
   - ✅ 文档末尾应该有额外的 `{n}` 锚点

## 相关文档

1. **[DOUBLE_FIX_REPORT.md](DOUBLE_FIX_REPORT.md)** - 详细修复报告
2. **[SURYA_OCR_PAGE_NUMBER_GUIDE.md](SURYA_OCR_PAGE_NUMBER_GUIDE.md)** - Surya + OCR 完整指南
3. **[FIX_COMPLETE.md](FIX_COMPLETE.md)** - 第一次修复报告
4. **[PIPELINE_VERIFICATION_REPORT.md](PIPELINE_VERIFICATION_REPORT.md)** - Pipeline 验证报告

## 修改的文件

1. ✅ [marker/scripts/streamlit_app.py](marker/scripts/streamlit_app.py:2028-2029)
2. ✅ [marker/renderers/markdown.py](marker/renderers/markdown.py:100-102)
3. ✅ [marker/renderers/markdown.py](marker/renderers/markdown.py:300-305)

## 下一步

现在你可以：
1. ✅ 重新运行 PDF 转换
2. ✅ 使用 Surya + 禁用 OCR 配置（如果 PDF 有文本层）
3. ✅ 正常提取印刷页码
4. ✅ 获得正确格式的页码锚点

## 总结

### 修复内容
- ✅ 修复了变量名映射错误
- ✅ 修复了双层括号问题
- ✅ 验证了所有测试通过

### 现在可以正常使用
- ✅ Surya + 禁用 OCR（有 PDF 文本层）
- ✅ Surya + Surya OCR（扫描件）
- ✅ 印刷页码识别
- ✅ 自定义编号系统

### 输出格式正确
- ✅ 页码锚点: `{0}`, `{1}`, `{2}`
- ✅ 页码标签: `<!-- Page: XII -->`
- ✅ 文档末尾锚点: `{n}`

**所有问题已解决，可以正常使用！** 🎉
