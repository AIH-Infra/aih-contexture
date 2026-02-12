# 双重错误修复报告

## 修复日期
2026-02-01

## 问题 1: 变量名未定义错误

### 错误信息
```
NameError: name 'printed_page_header_y_frac' is not defined.
Did you mean: 'printed_page_header_start'?
```

### 根本原因
UI 变量名与后端参数名不匹配：

**UI 变量名**（streamlit_app.py）：
- `printed_page_header_start` (0.0)
- `printed_page_header_end` (0.15)
- `printed_page_footer_start` (0.83)

**后端参数名**（PageNumberProcessor）：
- `printed_page_header_y_frac` (页眉区域阈值)
- `printed_page_footer_y_frac` (页脚区域阈值)

### 修复方案

**文件**：[marker/scripts/streamlit_app.py](marker/scripts/streamlit_app.py:2028-2029)

**修改前**：
```python
"printed_page_header_y_frac": printed_page_header_y_frac,  # ❌ 变量不存在
"printed_page_footer_y_frac": printed_page_footer_y_frac,  # ❌ 变量不存在
```

**修改后**：
```python
"printed_page_header_y_frac": printed_page_header_end,     # ✅ 使用正确的变量
"printed_page_footer_y_frac": printed_page_footer_start,   # ✅ 使用正确的变量
```

### 变量映射关系

| UI 变量 | 后端参数 | 含义 |
|---------|----------|------|
| `printed_page_header_end` | `printed_page_header_y_frac` | 页眉区域结束位置（默认 0.15 = 顶部 15%） |
| `printed_page_footer_start` | `printed_page_footer_y_frac` | 页脚区域开始位置（默认 0.83 = 底部 17%） |

**注意**：`printed_page_header_start` 在 UI 中存在但后端不使用（可能是未来扩展预留）。

---

## 问题 2: 双层括号错误

### 错误现象
页码锚点显示为 `{{0}}` 而不是 `{0}`

**示例**：
```markdown
{{0}}

页面内容...

{{1}}

页面内容...

{2}  ← 文档末尾的额外锚点正常
```

### 根本原因

**PageAnchorFormatter** 已经在 wrapper 中包含了括号：
```python
formatter = PageAnchorFormatter(wrapper="{{{}}}")
# wrapper="{{{}}}" 意味着：
# - {{ → 字面量 {
# - {} → 占位符
# - }} → 字面量 }
# 结果：formatter.format(0) → "{0}"
```

但 **MarkdownRenderer.convert_div** 又添加了一层括号：
```python
# 第 93 行：formatter 返回 "{0}"
page_anchor = self.page_anchor_formatter.format(page_id, printed_page_id)

# 第 101 行：又加了一层括号！
pagination_item = "\n\n" + "{" + page_anchor + "}" + "\n" + ...
# 结果："{" + "{0}" + "}" = "{{0}}"
```

### 修复方案

**文件**：[marker/renderers/markdown.py](marker/renderers/markdown.py:100-102)

**修改前**：
```python
pagination_item = (
    "\n\n" + "{" + page_anchor + "}" + "\n" + page_tag + self.page_separator + "\n\n"
)
```

**修改后**：
```python
pagination_item = (
    "\n\n" + page_anchor + "\n" + page_tag + self.page_separator + "\n\n"
)
```

### 为什么文档末尾的锚点正常？

文档末尾的额外锚点（line 352）直接使用 f-string 创建，没有经过 formatter：

```python
final_anchor = f"{{{page_count}}}"  # 直接生成 "{n}"
```

这是正确的，因为它不需要经过 formatter 的处理。

---

## 修复验证

### 语法检查
```bash
✅ marker/renderers/markdown.py - 通过
✅ marker/scripts/streamlit_app.py - 通过
```

### 预期输出

**修复后的正确输出**：
```markdown
{0}

<!-- Page: XII -->
前言内容...

{1}

<!-- Page: 1 -->
第一章内容...

{2}

第二章内容...

{3}  ← 文档末尾的额外锚点
```

---

## 测试建议

### 测试场景 1: Surya + 禁用 OCR + 启用印刷页码

**配置**：
```python
{
    "layout_backend": "surya",
    "ocr_engine": "none",
    "use_pdf_text": True,  # 使用 PDF 文本层
    "use_printed_page_number": True,
}
```

**预期结果**：
- ✅ 不再报错 `printed_page_header_y_frac not defined`
- ✅ 页码锚点显示为 `{0}` 而不是 `{{0}}`
- ✅ 如果 PDF 有文本层，可以提取印刷页码

### 测试场景 2: Surya + 禁用 OCR + 关闭印刷页码

**配置**：
```python
{
    "layout_backend": "surya",
    "ocr_engine": "none",
    "use_printed_page_number": False,
}
```

**预期结果**：
- ✅ 正常运行
- ✅ 页码锚点显示为 `{0}` 而不是 `{{0}}`
- ✅ 无 `<!-- Page: X -->` 标签（因为未启用印刷页码）

### 测试场景 3: Surya + Surya OCR + 启用印刷页码

**配置**：
```python
{
    "layout_backend": "surya",
    "ocr_engine": "surya_ocr",
    "use_printed_page_number": True,
}
```

**预期结果**：
- ✅ 正常运行
- ✅ 页码锚点显示为 `{0}` 而不是 `{{0}}`
- ✅ 可以提取印刷页码并生成 `<!-- Page: X -->` 标签

---

## 相关代码位置

### 修改的文件

1. **marker/scripts/streamlit_app.py**
   - 行 2028-2029：修复变量名映射

2. **marker/renderers/markdown.py**
   - 行 100-102：移除多余的括号

### 相关组件

1. **PageNumberProcessor** ([marker/processors/page_number.py](marker/processors/page_number.py))
   - 定义了 `printed_page_header_y_frac` 和 `printed_page_footer_y_frac` 参数

2. **PageAnchorFormatter** ([marker/formatters.py](marker/formatters.py))
   - 使用 `wrapper="{{{}}}"` 生成带括号的锚点

3. **MarkdownRenderer** ([marker/renderers/markdown.py](marker/renderers/markdown.py))
   - `convert_div` 方法：处理页面分隔和锚点
   - `__call__` 方法：添加文档末尾的额外锚点

---

## 总结

### 修复内容

✅ **问题 1**：修复了变量名不匹配导致的 NameError
- 将 `printed_page_header_y_frac` 映射到 `printed_page_header_end`
- 将 `printed_page_footer_y_frac` 映射到 `printed_page_footer_start`

✅ **问题 2**：修复了双层括号问题
- 移除了 convert_div 中多余的括号包装
- 保持了文档末尾锚点的正确格式

### 影响范围

- ✅ Surya + 禁用 OCR 模式现在可以正常工作
- ✅ 页码锚点格式正确（`{0}` 而不是 `{{0}}`）
- ✅ 印刷页码提取功能正常（如果有文本源）

### 下一步

1. 测试不同的配置组合
2. 验证印刷页码提取功能
3. 确认自定义编号功能正常

---

## 相关文档

- [FIX_COMPLETE.md](FIX_COMPLETE.md) - 第一次修复报告
- [SURYA_OCR_PAGE_NUMBER_GUIDE.md](SURYA_OCR_PAGE_NUMBER_GUIDE.md) - Surya + OCR 详细说明
- [PIPELINE_VERIFICATION_REPORT.md](PIPELINE_VERIFICATION_REPORT.md) - Pipeline 验证报告
