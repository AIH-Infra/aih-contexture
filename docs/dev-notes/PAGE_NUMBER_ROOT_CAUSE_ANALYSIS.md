# Surya + 禁用 OCR 无法提取印刷页码的根本原因

## 问题现象

使用 **Surya + 禁用 OCR** 模式时，即使勾选"提取印刷页码"选项，输出的 Markdown 中仍然没有印刷页码（`<!-- Page: X -->` 标签）。

## 根本原因

这是一个**架构限制**，不是 bug。原因如下：

### 1. Surya 的功能范围

Surya 是一个**布局检测模型**，它只能：
- ✅ 识别页面上有哪些区域（WHERE）
- ✅ 识别每个区域的类型（WHAT TYPE）：标题、正文、页眉、页脚等
- ❌ **不能读取文本内容**（WHAT TEXT）

### 2. PageNumberProcessor 的工作原理

查看 `marker/processors/page_number.py` 的代码：

```python
# 第 256 行：获取块的文本内容
text = self._get_block_text(block, document)

# 第 287-288 行：从块中提取文本
if hasattr(block, "text") and block.text:
    texts.append(block.text)
elif hasattr(block, "html") and block.html:
    text = re.sub(r"<[^>]+>", "", block.html)
    texts.append(text)
```

PageNumberProcessor 需要：
1. 找到页眉/页脚区域的块（Surya 可以提供）
2. **读取这些块的文本内容**（Surya 无法提供）
3. 从文本中解析页码（如 "Page 1", "第1页"）

### 3. 文本提取的来源

文本内容只能来自两个地方：
1. **PDF 自带的文本层**（原生 PDF）
2. **OCR 识别**（扫描版 PDF）

### 4. Surya + 禁用 OCR 的结果

```
Surya 布局检测 → 识别出页眉/页脚区域
                ↓
            没有文本提取
                ↓
        block.text = None
        block.html = None
                ↓
    PageNumberProcessor 无法解析页码
```

## 解决方案

### 方案 1：启用 OCR（推荐）

在 Streamlit UI 中：
1. 保持 Surya 布局检测
2. **启用 OCR**（勾选"使用 OCR"）
3. 勾选"提取印刷页码"

这样：
- Surya 识别页眉/页脚区域
- OCR 提取这些区域的文本
- PageNumberProcessor 从文本中解析页码

### 方案 2：使用原生 PDF

如果 PDF 本身有文本层（不是扫描版）：
1. 使用 Surya 布局检测
2. 禁用 OCR（因为 PDF 已有文本）
3. 勾选"提取印刷页码"

这样：
- Surya 识别页眉/页脚区域
- 从 PDF 文本层提取文本
- PageNumberProcessor 从文本中解析页码

### 方案 3：接受限制

如果必须使用 Surya + 禁用 OCR：
- 不勾选"提取印刷页码"
- 接受只有机器页码 `{0}`, `{1}`, `{2}` ...
- 没有 `<!-- Page: X -->` 标签

## 验证方法

### 检查 PDF 是否有文本层

```bash
# 使用 pdftotext 工具
pdftotext your_file.pdf - | head -20

# 如果输出有文本内容 → PDF 有文本层，可以禁用 OCR
# 如果输出为空或乱码 → PDF 是扫描版，必须启用 OCR
```

### 检查配置是否正确传递

在 `marker/processors/page_number.py` 的 `__call__` 方法中添加调试日志：

```python
def __call__(self, document: Document):
    if not self.page_numbering_enabled:
        logger.info("[PageNumberProcessor] Disabled by config")
        return

    logger.info(f"[PageNumberProcessor] Enabled, use_printed_page_number={self.use_printed_page_number}")
    logger.info(f"[PageNumberProcessor] Zones: {self.printed_page_zones}")
    # ...
```

## 总结

| 配置 | 布局检测 | 文本提取 | 印刷页码提取 |
|------|---------|---------|-------------|
| Surya + 禁用 OCR | ✅ | ❌ | ❌ |
| Surya + 启用 OCR | ✅ | ✅ | ✅ |
| 原生 PDF + 禁用 OCR | ✅ | ✅ | ✅ |

**结论：Surya + 禁用 OCR 无法提取印刷页码是正常的架构限制，不是 bug。**
