# 印刷页码提取问题修复总结

## 已修复的问题

### 1. PageNumberProcessor 未集成到 PdfConverter
**问题：** PageNumberProcessor 没有被导入和注册
**修复：** 在 `marker/converters/pdf.py` 中添加了导入和注册

### 2. _get_block_text 使用错误的属性名
**问题：** 使用 `children` 而不是 `structure` 来访问子块
**修复：** 修改为使用 `structure` 属性

### 3. UI 条件判断错误
**问题：** 检查 `conversion_mode == "pipeline"`，但实际值是 `"traditional"`
**修复：** 修改为 `conversion_mode == "traditional"`

### 4. 添加了详细的调试日志
**修复：** 在 PageNumberProcessor 中添加了 INFO 级别的日志，显示：
- 页面块的数量和类型
- 是否找到 PageHeader/PageFooter
- 候选块的文本内容
- 页码解析结果

## 当前状态

修复后，在 Pipeline 模式下勾选"提取印刷页码"应该：
1. ✅ 显示详细配置选项（页码搜索区域、页码格式等）
2. ✅ 配置正确传递到 PageNumberProcessor
3. ✅ 日志显示 `use_printed_page_number=True`

## 诊断步骤

### 步骤 1：确认 UI 配置

刷新 Streamlit 页���后：
1. 选择 **"传统模式（Marker Pipeline）"**
2. 勾选 **"启用页码锚点"**
3. 勾选 **"提取印刷页码"**
4. **应该显示详细配置选项**：
   - 页码搜索区域
   - 页码格式
   - 页眉/页脚位置滑块

### 步骤 2：配置参数

推荐配置：
- 页码搜索区域：`header` 和 `footer`
- 页码格式：`auto`（自动检测）
- 其他参数使用默认值

### 步骤 3：运行转换并查看日志

运行转换后，查看日志中的关键信息：

#### ✅ 正确的日志输出：

```
[PageNumberProcessor] ✅ Enabled, processing 5 pages
[PageNumberProcessor] Config: use_printed_page_number=True  ← 应该是 True
[PageNumberProcessor] Config: zones=['footer', 'header']
[PageNumberProcessor] Config: format=auto

[PageNumberProcessor] Page has 10 blocks
[PageNumberProcessor] Block types on page: BlockTypes.Text, BlockTypes.Text, ...
[PageNumberProcessor] No PageHeader/PageFooter blocks found, using coordinate heuristics
[PageNumberProcessor] Header threshold: 123.45, Footer threshold: 678.90
[PageNumberProcessor] Found block in header region: BlockTypes.Text

[PageNumberProcessor] Candidate 0: block_type=BlockTypes.Text, text='127'
[PageNumberProcessor] Successfully parsed page number: '127'
[PageNumberProcessor] Page 0: Found printed page number '127'

[PageNumberProcessor] Completed: 5/5 pages with printed numbers
```

#### ❌ 错误的日志输出：

**情况 1：配置未启用**
```
[PageNumberProcessor] Config: use_printed_page_number=False  ← 错误！
[PageNumberProcessor] Completed: 0/5 pages with printed numbers
```
→ 说明配置没有正确传递

**情况 2：找不到候选块**
```
[PageNumberProcessor] Config: use_printed_page_number=True
[PageNumberProcessor] Page has 10 blocks
[PageNumberProcessor] Block types on page: BlockTypes.Text, BlockTypes.Text, ...
[PageNumberProcessor] No PageHeader/PageFooter blocks found, using coordinate heuristics
[PageNumberProcessor] Header threshold: 123.45, Footer threshold: 678.90
(没有 "Found block in header region" 的日志)
```
→ 说明页眉/页脚区域没有找到块，可能需要调整阈值

**情况 3：块中没有文本**
```
[PageNumberProcessor] Candidate 0: block_type=BlockTypes.Text, text='EMPTY'
```
→ 说明块中没有文本内容，可能是文本提取失败

**情况 4：页码解析失败**
```
[PageNumberProcessor] Candidate 0: block_type=BlockTypes.Text, text='Entstehung der Theologischen Briefe. 127'
[PageNumberProcessor] Could not parse page number from text: 'Entstehung der Theologischen Briefe. 127'
```
→ 说明文本中有页码，但解析失败

## 下一步

请提供以下信息：

1. **UI 截图**：显示详细配置选项是否出现
2. **完整日志输出**：特别是 `[PageNumberProcessor]` 相关的所有日志
3. **输出预览**：Markdown 输出的前 500 字符

根据这些信息，我可以准确诊断问题所在。

## 测试 PDF 信息

根据之前的测试：
- PDF 有文本层 ✅
- 页码格式：纯数字（127, 128）
- 页码位置：页眉（页面顶部）
- 示例文本：
  - 页面 2: `Entstehung der Theologischen Briefe. 127`
  - 页面 3: `128 Die Theologischen Briefe.`

页码应该可以被 `_parse_arabic` 方法识别。
