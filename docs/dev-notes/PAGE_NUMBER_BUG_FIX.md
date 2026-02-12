# 印刷页码提取问题的根本原因和修复

## 问题现象

即使勾选了"提取印刷页码"选项，Surya + 禁用 OCR 模式下仍然无法提取印刷页码。

## 根本原因

经过深入追踪代码流程，发现了真正的 bug：

### 数据流程

1. **LayoutBuilder** (marker/builders/layout.py:131-154)
   - Surya 识别布局，创建 PageHeader/PageFooter 块
   - 只设置块的位置和类型，**不包含文本**

2. **LineBuilder** (marker/builders/line.py:346-369)
   - 从 PDF 文本层提取文本行
   - 将文本行添加到块的 **`structure`** 属性中
   - 文本存储在 Line 和 Span 子块中

3. **PageNumberProcessor** (marker/processors/page_number.py:283-312)
   - 尝试从 PageHeader/PageFooter 块中提取文本
   - **BUG**: 使用了错误的属性名 `children` 而不是 `structure`

### 代码 Bug

在 [marker/processors/page_number.py:297](marker/processors/page_number.py#L297)：

```python
# ❌ 错误的代码
if hasattr(block, "children") and block.children:
    for child_id in block.children:
        ...
```

但是根据 [marker/schema/blocks/base.py:90-92](marker/schema/blocks/base.py#L90-L92)：

```python
class Block(BaseModel):
    structure: List[BlockId] | None = None  # ← 子块存储在这里！
```

**块的子结构存储在 `structure` 属性中，不是 `children`！**

因此，PageNumberProcessor 无法遍历子块（Line/Span），也就无法提取文本。

## 修复方案

修改 [marker/processors/page_number.py:297](marker/processors/page_number.py#L297)：

```python
# ✅ 修复后的代码
if hasattr(block, "structure") and block.structure:
    for child_id in block.structure:
        child = document.get_block(child_id)
        if child:
            child_text = self._get_block_text(child, document)
            if child_text:
                texts.append(child_text)
```

## 完整的数据结构

```
PageHeader 块
├── structure: [Line1_id, Line2_id, ...]  ← 子块列表
│   ├── Line1
│   │   ├── structure: [Span1_id, Span2_id, ...]
│   │   │   ├── Span1
│   │   │   │   └── text: "Page"  ← 实际文本在这里
│   │   │   └── Span2
│   │   │       └── text: "1"
│   │   └── ...
│   └── Line2
│       └── ...
└── html: None  ← 在处理器阶段还没有设置
```

## 为什么之前没有发现

1. **VLM Direct 模式可能工作正常**
   - VLM Direct 可能使用不同的数据结构
   - 或者直接设置了 `.html` 属性

2. **测试覆盖不足**
   - 可能没有测试 Surya + 禁用 OCR + 提取印刷页码的组合

3. **属性名混淆**
   - `children` vs `structure` 容易混淆
   - 没有类型检查会导致运行时才发现问题

## 验证修复

运行转换后，查看日志应该显示：

```
[PageNumberProcessor] ✅ Enabled, processing 10 pages
[PageNumberProcessor] Config: use_printed_page_number=True
[PageNumberProcessor] Found 2 candidate blocks
[PageNumberProcessor] Candidate 0: block_type=PageFooter, text='Page 1'
[PageNumberProcessor] Successfully parsed page number: '1'
[PageNumberProcessor] Page 0: Found printed page number '1'
...
[PageNumberProcessor] Completed: 10/10 pages with printed numbers
```

## 总结

**问题不是配置问题，而是代码 bug：**
- ❌ 不是"提取印刷页码"选项未勾选
- ❌ 不是 Surya + 禁用 OCR 的架构限制
- ✅ **是 PageNumberProcessor 使用了错误的属性名 `children` 而不是 `structure`**

修复后，Surya + 禁用 OCR 模式应该可以正常提取印刷页码（前提是 PDF 有文本层）。
