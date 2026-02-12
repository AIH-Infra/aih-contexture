# 双层括号问题诊断指南

## 测试结果

✅ **代码已正确修复**

所有测试场景都通过：
- 禁用印刷页码：`{0}` ✓
- 启用印刷页码（无法提取）：`{1}` ✓
- 启用印刷页码（成功提取）：`{2}` + `<!-- Page: XII -->` ✓
- 使用自定义编号：`{3}` + `<!-- Page: sc004 -->` ✓
- 文档末尾锚点：`{5}` ✓

## 如果仍然看到 `{{1}}`

### 步骤 1: 重启 Streamlit 应用

**问题**：Python 可能缓存了旧的代码

**解决方案**：
```bash
# 停止当前运行的 Streamlit
# 按 Ctrl+C

# 重新启动
cd d:\marker_cuda
streamlit run marker\scripts\streamlit_app.py
```

### 步骤 2: 清除浏览器缓存

**问题**：浏览器可能缓存了旧的输出

**解决方案**：
1. 按 `Ctrl + Shift + R` 强制刷新页面
2. 或者清除浏览器缓存
3. 或者使用无痕模式打开

### 步骤 3: 删除旧的输出文件

**问题**：可能在查看之前生成的旧文件

**解决方案**：
```bash
# 删除旧的输出文件
cd d:\marker_cuda
del *.md  # 删除所有 markdown 文件
```

然后重新运行转换。

### 步骤 4: 验证代码版本

**检查修复是否已应用**：

```bash
cd d:\marker_cuda
python test_disabled_printed_pages.py
```

**预期输出**：
```
[OK] 无双层括号
[OK] 无双层括号
[OK] 无双层括号
[OK] 无双层括号
[OK] 无双层括号
```

如果看到 `[FAIL]`，说明代码未正确更新。

### 步骤 5: 检查文件修改时间

**验证文件是否已更新**：

```bash
# Windows
dir marker\renderers\markdown.py
dir marker\scripts\streamlit_app.py

# 检查修改时间是否是今天
```

**关键文件**：
1. `marker/renderers/markdown.py` - 行 100-102
2. `marker/scripts/streamlit_app.py` - 行 2028-2029

### 步骤 6: 手动验证修复

**检查 markdown.py 第 100-102 行**：

应该是：
```python
pagination_item = (
    "\n\n" + page_anchor + "\n" + page_tag + self.page_separator + "\n\n"
)
```

**不应该是**（旧代码）：
```python
pagination_item = (
    "\n\n" + "{" + page_anchor + "}" + "\n" + page_tag + self.page_separator + "\n\n"
)
```

## 关于印刷页码不显示的问题

### 原因分析

**配置**：Surya + 禁用 OCR + 启用印刷页码

**问题**：无法显示 `<!-- Page: X -->` 标签

**原因**：
1. **Surya 只检测位置**，不读取文本
2. **禁用 OCR** = 没有文本内容
3. **没有文本** = 无法提取印刷页码
4. **结果**：只有 `{n}` 锚点，没有 `<!-- Page: X -->` 标签

### 解决方案

#### 方案 1: 启用 PDF 文本层（推荐）

如果 PDF 是电子文档（有内嵌文本）：

```python
{
    "layout_backend": "surya",
    "ocr_engine": "none",
    "use_pdf_text": True,  # ← 关键！
    "use_printed_page_number": True,
}
```

**在 UI 中**：
- 禁用 OCR ✓
- 启用"使用 PDF 文本层"✓
- 启用"提取印刷页码"✓

#### 方案 2: 启用 OCR

如果 PDF 是扫描件（无内嵌文本）：

```python
{
    "layout_backend": "surya",
    "ocr_engine": "surya_ocr",  # ← 关键！
    "use_printed_page_number": True,
}
```

**在 UI 中**：
- 启用 OCR（选择 Surya OCR）✓
- 启用"提取印刷页码"✓

#### 方案 3: 使用自定义编号

如果无法提取印刷页码：

```python
{
    "layout_backend": "surya",
    "ocr_engine": "none",
    "use_printed_page_number": False,
    "custom_id_source": "auto",
    "custom_id_data": {
        "prefix": "page",
        "start": 1,
        "digits": 3
    }
}
```

**在 UI 中**：
- 禁用 OCR ✓
- 关闭"提取印刷页码"✓
- 自定义编号来源：选择"自动生成"✓
- 配置前缀、起始编号、位数

## 预期输出对比

### 场景 1: Surya + 禁用 OCR + 禁用印刷页码

**配置**：
- `ocr_engine="none"`
- `use_pdf_text=False`
- `use_printed_page_number=False`

**输出**：
```markdown
{0}

页面内容...

{1}

页面内容...
```

**特点**：
- ✅ 单层括号 `{0}`
- ❌ 无 `<!-- Page: X -->` 标签（因为禁用了印刷页码）

### 场景 2: Surya + 禁用 OCR + 启用印刷页码（无文本）

**配置**：
- `ocr_engine="none"`
- `use_pdf_text=False`
- `use_printed_page_number=True`

**输出**：
```markdown
{0}

页面内容...

{1}

页面内容...
```

**特点**：
- ✅ 单层括号 `{0}`
- ❌ 无 `<!-- Page: X -->` 标签（因为没有文本可提取）

### 场景 3: Surya + 禁用 OCR + 启用印刷页码（有 PDF 文本）

**配置**：
- `ocr_engine="none"`
- `use_pdf_text=True`  # ← 关键
- `use_printed_page_number=True`

**输出**：
```markdown
{0}

<!-- Page: XII -->
页面内容...

{1}

<!-- Page: 1 -->
页面内容...
```

**特点**：
- ✅ 单层括号 `{0}`
- ✅ 有 `<!-- Page: X -->` 标签（从 PDF 文本层提取）

### 场景 4: Surya + Surya OCR + 启用印刷页码

**配置**：
- `ocr_engine="surya_ocr"`  # ← 关键
- `use_printed_page_number=True`

**输出**：
```markdown
{0}

<!-- Page: 42 -->
页面内容...

{1}

<!-- Page: 43 -->
页面内容...
```

**特点**：
- ✅ 单层括号 `{0}`
- ✅ 有 `<!-- Page: X -->` 标签（OCR 识别）

## 快速诊断命令

```bash
# 1. 测试代码是否正确
cd d:\marker_cuda
python test_disabled_printed_pages.py

# 2. 检查文件修改
git diff marker/renderers/markdown.py
git diff marker/scripts/streamlit_app.py

# 3. 重新编译检查语法
python -m py_compile marker/renderers/markdown.py
python -m py_compile marker/scripts/streamlit_app.py

# 4. 重启 Streamlit
# Ctrl+C 停止
streamlit run marker\scripts\streamlit_app.py
```

## 总结

### 双层括号问题

✅ **已修复** - 代码测试全部通过

如果仍然看到 `{{1}}`：
1. 重启 Streamlit 应用
2. 清除浏览器缓存
3. 删除旧的输出文件
4. 验证代码版本

### 印刷页码不显示问题

❌ **这是预期行为** - Surya + 禁用 OCR 无法提取文本

解决方案：
1. 启用 `use_pdf_text=True`（如果 PDF 有文本层）
2. 启用 OCR（如果是扫描件）
3. 使用自定义编号（如果无法提取）

## 相关文档

- [FINAL_FIX_SUMMARY.md](FINAL_FIX_SUMMARY.md) - 完整修复总结
- [SURYA_OCR_PAGE_NUMBER_GUIDE.md](SURYA_OCR_PAGE_NUMBER_GUIDE.md) - Surya + OCR 详细指南
- [test_disabled_printed_pages.py](test_disabled_printed_pages.py) - 测试脚本
