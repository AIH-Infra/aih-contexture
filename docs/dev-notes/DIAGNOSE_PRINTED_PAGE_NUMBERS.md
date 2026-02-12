# 诊断印刷页码提取问题

## 问题：Surya + 禁用 OCR 模式下没有印刷页码

您的 PDF 是**原生 PDF（有文本层）**，理论上应该可以提取印刷页码。

## 诊断步骤

### 步骤 1：检查 UI 配置

在 Streamlit UI 中，确保以下选项已正确配置：

#### 必须勾选的选项：
1. **✅ "提取印刷页码"** - 这个选项默认是**未勾选**的！
   - 位置：在"页码锚点配置"区域
   - 如果不勾选，PageNumberProcessor 的 `use_printed_page_number` 会是 False
   - 即使 PageNumberProcessor 运行了，也不会提取印刷页码

#### 可选配置：
2. **页码搜索区域** - 默认是 ["footer", "header"]
   - 如果您的 PDF 页码在特殊位置（如右上角），需要调整这个配置
   - 可选值：header, footer, top-right, bottom-right, top-left, bottom-left

3. **页码格式** - 默认是 "arabic"（阿拉伯数字）
   - 如果您的 PDF 使用罗马数字或中文数字，需要调整

### 步骤 2：查看日志输出

运行转换后，查看日志中的以下信息：

#### 正常情况（已启用）：
```
[PageNumberProcessor] ✅ Enabled, processing 10 pages
[PageNumberProcessor] Config: use_printed_page_number=True
[PageNumberProcessor] Config: zones=['footer', 'header']
[PageNumberProcessor] Config: format=arabic
[PageNumberProcessor] Page 0: Found printed page number '1'
[PageNumberProcessor] Page 1: Found printed page number '2'
...
[PageNumberProcessor] Completed: 10/10 pages with printed numbers
```

#### 未启用的情况：
```
[PageNumberProcessor] ❌ Disabled by page_numbering_enabled=False
```
→ 说明 PageNumberProcessor 被禁用了（这是正常的，因为它默认禁用）

#### 启用但未提取的情况：
```
[PageNumberProcessor] ✅ Enabled, processing 10 pages
[PageNumberProcessor] Config: use_printed_page_number=False
```
→ 说明勾选了"启用页码处理"，但**没有勾选"提取印刷页码"**

#### 启用但找不到页码：
```
[PageNumberProcessor] ✅ Enabled, processing 10 pages
[PageNumberProcessor] Config: use_printed_page_number=True
[PageNumberProcessor] Page 0: No printed page number found
[PageNumberProcessor] Page 1: No printed page number found
...
[PageNumberProcessor] Completed: 0/10 pages with printed numbers
```
→ 说明配置正确，但在指定区域找不到页码

### 步骤 3：如果找不到页码

如果日志显示 "No printed page number found"，可能的原因：

1. **搜索区域不正确**
   - 您的 PDF 页码可能不在页眉/页脚
   - 尝试添加其他搜索区域：top-right, bottom-right 等

2. **页码格式不匹配**
   - 您的 PDF 可能使用罗马数字（I, II, III）或中文数字（一、二、三）
   - 尝试更改"页码格式"配置

3. **页码区域阈值不正确**
   - 默认页眉区域：页面顶部 15%
   - 默认页脚区域：页面底部 17%（从 83% 开始）
   - 如果页码在这些区域之外，需要调整阈值

### 步骤 4：启用详细调试日志

如果仍然找不到原因，可以启用详细调试日志：

在运行转换前，设置环境变量：
```bash
export MARKER_DEBUG=1
```

或在代码中设置：
```python
import logging
logging.getLogger("marker.processors.page_number").setLevel(logging.DEBUG)
```

这会输出更详细的信息：
```
[PageNumberProcessor] Found 3 candidate blocks
[PageNumberProcessor] Candidate 0: block_type=PageFooter, text='Page 1'
[PageNumberProcessor] Successfully parsed page number: '1'
```

## 快速检查清单

- [ ] 勾选了"提取印刷页码"选项
- [ ] 页码搜索区域包含了 PDF 页码的实际位置
- [ ] 页码格式与 PDF 实际格式匹配
- [ ] 查看日志确认 `use_printed_page_number=True`
- [ ] 查看日志确认找到了候选块
- [ ] 查看日志确认成功解析了页码

## 最可能的原因

根据经验，**最常见的原因是忘记勾选"提取印刷页码"选项**。

这个选项在 UI 中默认是**未勾选**的，即使勾选了"启用页码处理"，也需要单独勾选"提取印刷页码"。

## 测试建议

1. 先用一个简单的 PDF 测试（页码在页脚中央，格式为 "1", "2", "3"）
2. 确认配置正确后，再处理复杂的 PDF
3. 如果某个 PDF 无法提取页码，可以手动检查该 PDF 的页码位置和格式
