# 印刷页码提取配置检查清单

## 问题诊断

根据日志输出：
```
[PageNumberProcessor] Config: use_printed_page_number=False
```

**配置显示 `use_printed_page_number=False`，说明"提取印刷页码"选项未启用。**

## 解决方案

### 步骤 1：确认勾选"提取印刷页码"

在 Streamlit UI 中：

1. 选择 **Pipeline 模式**（不是 VLM Direct 模式）
2. 找到 **"页码锚点配置"** 区域
3. 勾选 **"启用页码锚点"** 复选框
4. 勾选 **"提取印刷页码"** 复选框 ← **关键步骤！**

### 步骤 2：配置页码搜索区域

勾选"提取印刷页码"后，会出现详细配置：

- **页码搜索区域**：选择 `footer` 和 `header`（默认值）
- **页码格式**：选择 `auto`（自动检测）或 `arabic`（阿拉伯数字）

### 步骤 3：运行转换

点击"开始转换"按钮。

### 步骤 4：检查日志

在日志输出中查找：

```
[PageNumberProcessor] ✅ Enabled, processing X pages
[PageNumberProcessor] Config: use_printed_page_number=True  ← 应该是 True
[PageNumberProcessor] Config: zones=['footer', 'header']
[PageNumberProcessor] Config: format=arabic
```

**如果看到 `use_printed_page_number=False`，说明"提取印刷页码"选项未勾选。**

## 常见问题

### Q1: 我明明勾选了，为什么还是 False？

**可能原因：**
1. 勾选后又取消了
2. 切换了转换模式（Pipeline ↔ VLM Direct），导致配置重置
3. 刷新了页面，配置丢失

**解决方法：**
- 重新勾选"提取印刷页码"
- 确认勾选后立即运行转换
- 不要在勾选后切换转换模式

### Q2: 勾选后日志显示 True，但还是没有印刷页码？

**可能原因：**
1. Surya 没有识别出 PageHeader/PageFooter 块
2. 页码文本不在页眉/页脚区域
3. 页码格式不匹配解析规则

**解决方法：**
- 查看日志中的 `[PageNumberProcessor] Block types on page: ...`
- 查看日志中的 `[PageNumberProcessor] Candidate X: block_type=..., text='...'`
- 根据日志调整配置

### Q3: 如何确认配置是否生效？

**检查日志输出：**

✅ **正确配置：**
```
[PageNumberProcessor] Config: use_printed_page_number=True
[PageNumberProcessor] Page has 10 blocks
[PageNumberProcessor] Block types on page: BlockTypes.Text, BlockTypes.Text, ...
[PageNumberProcessor] Found block in header region: BlockTypes.Text
[PageNumberProcessor] Candidate 0: block_type=BlockTypes.Text, text='127'
[PageNumberProcessor] Successfully parsed page number: '127'
[PageNumberProcessor] Page 0: Found printed page number '127'
```

❌ **错误配置：**
```
[PageNumberProcessor] Config: use_printed_page_number=False
[PageNumberProcessor] Completed: 0/5 pages with printed numbers
```

## 测试 PDF 的页码格式

根据测试，您的 PDF 页码格式：
- **位置**：页眉（页面顶部）
- **格式**：纯数字（127, 128, ...）
- **示例**：
  - 页面 2: `Entstehung der Theologischen Briefe. 127`
  - 页面 3: `128 Die Theologischen Briefe.`

**推荐配置：**
- 页码搜索区域：`header`（优先）和 `footer`
- 页码格式：`arabic`（阿拉伯数字）

## 快速测试步骤

1. ✅ 勾选"启用页码锚点"
2. ✅ 勾选"提取印刷页码"
3. ✅ 页码搜索区域：选择 `header` 和 `footer`
4. ✅ 页码格式：选择 `arabic`
5. ✅ 点击"开始转换"
6. ✅ 查看日志，确认 `use_printed_page_number=True`
7. ✅ 查看输出，确认有 `<!-- Page: 127 -->` 标签

## 总结

**最常见的问题：忘记勾选"提取印刷页码"选项。**

Pipeline 模式下，这个选项默认是**未勾选**的，必须手动勾选才能启用印刷页码提取。

请按照上述步骤重新配置并测试。
