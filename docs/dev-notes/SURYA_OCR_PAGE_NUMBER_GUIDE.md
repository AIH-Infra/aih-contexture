# Surya + OCR 与印刷页码识别关系说明

## 问题分析

### 错误原因

**错误信息**：
```
TypeError: PageAnchorFormatter.__init__() got an unexpected keyword argument 'template'
```

**根本原因**：
MarkdownRenderer 中还在使用旧的 PageAnchorFormatter API（`template` 和 `page_anchor_start` 参数），但这些参数已在简化更新中移除。

**已修复**：
- 移除了 `page_anchor_template` 和 `page_anchor_start` 类属性
- 更新 `md_cls` 属性使用新的简化 API：`PageAnchorFormatter(wrapper="{{{}}}")`

## 核心问题：Surya + 禁用 OCR 能否识别印刷页码？

### 简短回答

**❌ 不能**

Surya + 禁用 OCR **无法**识别印刷页码，因为：
- Surya 只检测**位置**（WHERE）
- OCR 才能读取**内容**（WHAT）
- 印刷页码识别需要**文本内容**

### 详细解释

## 1. Surya 的作用

**Surya 是什么**：
- 版面检测模型（Layout Detection）
- 识别页面结构和块类型

**Surya 能做什么**：
```
✅ 检测页眉位置（PageHeader 块）
✅ 检测页脚位置（PageFooter 块）
✅ 检测文本块、图片、表格等
✅ 提供边界框坐标
```

**Surya 不能做什么**：
```
❌ 读取文本内容
❌ 识别具体的页码数字
❌ 理解文本含义
```

**示例**：
```
Surya 输出：
{
  "type": "PageFooter",
  "bbox": [100, 750, 500, 800],  # 页脚位置
  "text": ???  # Surya 不提供文本！
}
```

## 2. OCR 的作用

**OCR 是什么**：
- 光学字符识别（Optical Character Recognition）
- 从图像中提取文本

**OCR 能做什么**：
```
✅ 读取图像中的文字
✅ 识别页码数字（1, 2, XII, 第一頁）
✅ 提供文本内容
```

**示例**：
```
OCR 输出：
{
  "bbox": [100, 750, 500, 800],
  "text": "Page 42"  # OCR 提供文本内容！
}
```

## 3. 印刷页码识别流程

### 完整流程（需要 OCR）

```
┌─────────────────────────────────────────────────────────┐
│  步骤 1: Surya Layout Detection                          │
│  - 检测页眉/页脚位置                                      │
│  - 输出: PageHeader/PageFooter 块 + 边界框               │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  步骤 2: OCR 文本识别                                     │
│  - 读取页眉/页脚区域的文本                                │
│  - 输出: "Page 42", "XII", "第一頁" 等                   │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  步骤 3: PageNumberProcessor                             │
│  - 从文本中提取页码                                       │
│  - 解析不同格式（阿拉伯、罗马、中文）                      │
│  - 输出: "42", "XII", "第一頁"                           │
└─────────────────────────────────────────────────────────┘
```

### 禁用 OCR 的情况

```
┌─────────────────────────────────────────────────────────┐
│  步骤 1: Surya Layout Detection                          │
│  - 检测页眉/页脚位置                                      │
│  - 输出: PageHeader/PageFooter 块 + 边界框               │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  步骤 2: OCR 文本识别 ❌ 禁用                            │
│  - 无文本内容                                            │
│  - 输出: 空                                              │
└─────────────────────────────────────────────────────────┘
                         ↓
┌────���────────────────────────────────────────────────────┐
│  步骤 3: PageNumberProcessor ❌ 失败                     │
│  - 没有文本可供提取                                       │
│  - 输出: None                                            │
└─────────────────────────────────────────────────────────┘
```

## 4. 特殊情况：PDF 内嵌文本

### 什么是内嵌文本？

有些 PDF 文件已经包含文本层（不是图像），例如：
- 电子出版物（直接从 Word/LaTeX 生成）
- 已经过 OCR 处理的扫描件
- 数字化文档

### 内嵌文本的情况

如果 PDF 有内嵌文本，可以：
```
✅ 不运行 OCR（节省时间）
✅ 直接读取 PDF 文本层
✅ 提取印刷页码
```

**但这不是"禁用 OCR"，而是"使用 PDF 文本层"**

### 配置示例

```python
# 场景 1: PDF 有内嵌文本（推荐）
config = {
    "ocr_engine": "none",  # 不运行 OCR
    "use_pdf_text": True,  # 使用 PDF 文本层
    "use_printed_page_number": True,  # 可以提取页码
}

# 场景 2: 完全禁用文本提取（无法识别页码）
config = {
    "ocr_engine": "none",  # 不运行 OCR
    "use_pdf_text": False,  # 不使用 PDF 文本层
    "use_printed_page_number": True,  # ❌ 无效，没有文本可提取
}
```

## 5. 实际场景分析

### 场景 1: 扫描件 PDF（无内嵌文本）

**文档特点**：
- 扫描的图像
- 无 PDF 文本层
- 需要 OCR 识别文字

**配置**：
```python
{
    "layout_backend": "surya",  # 使用 Surya 检测布局
    "ocr_engine": "surya_ocr",  # ✅ 必须启用 OCR
    "use_printed_page_number": True,
}
```

**结果**：
```
✅ Surya 检测页眉/页脚位置
✅ OCR 读取页眉/页脚文本
✅ PageNumberProcessor 提取页码
✅ 输出: <!-- Page: 42 -->
```

### 场景 2: 电子出版物 PDF（有内嵌文本）

**文档特点**：
- 电子生成的 PDF
- 有完整的文本层
- 不需要 OCR

**配置**：
```python
{
    "layout_backend": "surya",  # 使用 Surya 检测布局
    "ocr_engine": "none",  # ✅ 可以禁用 OCR
    "use_pdf_text": True,  # ✅ 使用 PDF 文本层
    "use_printed_page_number": True,
}
```

**结���**：
```
✅ Surya 检测页眉/页脚位置
✅ 直接读取 PDF 文本层
✅ PageNumberProcessor 提取页码
✅ 输出: <!-- Page: 42 -->
```

### 场景 3: Surya + 禁用所有文本提取

**配置**：
```python
{
    "layout_backend": "surya",  # 使用 Surya 检测布局
    "ocr_engine": "none",  # ❌ 禁用 OCR
    "use_pdf_text": False,  # ❌ 不使用 PDF 文本层
    "use_printed_page_number": True,
}
```

**结果**：
```
✅ Surya 检测页眉/页脚位置
❌ 无文本内容
❌ PageNumberProcessor 无法提取页码
❌ 输出: 仅 {n} 锚点，无 <!-- Page: X --> 标签
```

## 6. 解决方案

### 方案 1: 启用 OCR（推荐）

如果是扫描件，必须启用 OCR：

```python
config = {
    "layout_backend": "surya",
    "ocr_engine": "surya_ocr",  # 或 "tesseract"
    "use_printed_page_number": True,
}
```

### 方案 2: 使用 PDF 文本层

如果 PDF 有内嵌文本：

```python
config = {
    "layout_backend": "surya",
    "ocr_engine": "none",
    "use_pdf_text": True,  # 关键！
    "use_printed_page_number": True,
}
```

### 方案 3: 使用自定义编号

如果无法提取印刷页码，使用自定义编号：

```python
config = {
    "layout_backend": "surya",
    "ocr_engine": "none",
    "use_printed_page_number": False,  # 关闭自动识别
    "custom_id_source": "auto",
    "custom_id_data": {
        "prefix": "page",
        "start": 1,
        "digits": 3
    }
}
```

## 7. 常见误解

### 误解 1: "Surya 可以识别页码"

**错误**：认为 Surya 能读取页码数字

**正确**：
- Surya 只能检测页眉/页脚的**位置**
- 需要 OCR 读取**内容**
- PageNumberProcessor 从内容中**提取**页码

### 误解 2: "禁用 OCR 可以提高速度"

**部分正确**：
- 如果 PDF 有内嵌文本，可以禁用 OCR
- 但必须启用 `use_pdf_text`
- 完全禁用文本提取会失去很多功能

### 误解 3: "Surya 比 OCR 更准确"

**错误**：这是两个不同的任务
- Surya：布局检测（结构）
- OCR：文本识别（内容）
- 两者互补，不是替代关系

## 8. 最佳实践

### 推荐配置

**扫描件 PDF**：
```python
{
    "layout_backend": "surya",      # 布局检测
    "ocr_engine": "surya_ocr",      # 文本识别
    "use_printed_page_number": True, # 提取页码
}
```

**电子 PDF**：
```python
{
    "layout_backend": "surya",      # 布局检测
    "ocr_engine": "none",           # 不需要 OCR
    "use_pdf_text": True,           # 使用内嵌文本
    "use_printed_page_number": True, # 提取页码
}
```

**混合文档**：
```python
{
    "layout_backend": "surya",      # 布局检测
    "ocr_engine": "surya_ocr",      # OCR 作为后备
    "use_pdf_text": True,           # 优先使用内嵌文本
    "use_printed_page_number": True, # 提取页码
}
```

## 9. 性能对比

| 配置 | 速度 | 准确率 | 页码识别 |
|------|------|--------|----------|
| Surya + Surya OCR | 中等 | 高 | ✅ 支持 |
| Surya + Tesseract | 慢 | 中等 | ✅ 支持 |
| Surya + PDF 文本 | 快 | 最高 | ✅ 支持 |
| Surya + 禁用文本 | 最快 | N/A | ❌ 不支持 |

## 10. 总结

### 核心要点

1. **Surya ≠ OCR**
   - Surya：检测位置（WHERE）
   - OCR：读取内容（WHAT）

2. **印刷页码识别需要文本**
   - 来源 1：OCR 识别
   - 来源 2：PDF 内嵌文本
   - 来源 3：无（使用自定义编号）

3. **禁用 OCR 的正确理解**
   - 如果 PDF 有内嵌文本：可以禁用 OCR，但要启用 `use_pdf_text`
   - 如果 PDF 是扫描件：必须启用 OCR
   - 完全禁用文本提取：无法识别印刷页码

### 回答原问题

**问题 1**: "Surya + 禁用 OCR 不开启印刷页码报错怎么回事？"

**答案**：已修复。错误是因为 MarkdownRenderer 使用了旧的 API。现在已更新为新的简化 API。

**问题 2**: "在有良好 OCR 识别的基础上，Surya + 禁用 OCR 可以实现印刷页码吗？"

**答案**：
- 如果"良好 OCR 识别"指的是 **PDF 已有内嵌文本**：✅ 可以，但要启用 `use_pdf_text`
- 如果"良好 OCR 识别"指的是 **需要运行 OCR**：❌ 不可以，必须启用 OCR
- 如果"禁用 OCR"指的是 **完全不读取文本**：❌ 不可以，无法识别页码

### 建议

1. **扫描件**：必须启用 OCR
2. **电子 PDF**：可以禁用 OCR，但要启用 `use_pdf_text`
3. **无法识别页码**：使用 CustomIDInjector 自定义编号
4. **追求速度**：使用 PDF 文本层（如果有）
5. **追求准确率**：使用 Surya OCR

## 相关文档

- [PIPELINE_VERIFICATION_REPORT.md](PIPELINE_VERIFICATION_REPORT.md) - Pipeline 验证报告
- [UI_UPDATE_COMPLETE.md](UI_UPDATE_COMPLETE.md) - UI 更新报告
- [PAGE_ANCHOR_QUICKREF_V2.md](PAGE_ANCHOR_QUICKREF_V2.md) - 快速参考指南
