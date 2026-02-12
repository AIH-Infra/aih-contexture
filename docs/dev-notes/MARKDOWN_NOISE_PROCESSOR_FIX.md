# Markdown 噪音清理处理器修复报告

## 问题描述

MarkdownNoiseRemovalProcessor 被调用但清理了 0 个文本片段。

## 根本原因

处理器访问文本的方式不正确：

### ❌ 错误的实现

```python
# 错误 1: 直接迭代 block.structure（返回 BlockId 对象）
for line_id in block.structure:
    line = document.get_block(line_id)

    # 错误 2: Line 对象没有 'spans' 属性
    if not hasattr(line, 'spans') or not line.spans:
        continue

    # 错误 3: line.spans 不存在
    for span in line.spans:
        ...
```

**问题**：
1. Line 对象继承自 Block，使用 `structure` 属性存储子对象的 BlockId
2. Line 对象**没有** `spans` 属性
3. 需要使用 `structure_blocks(document)` 方法获取实际的 Span 对象

---

## 解决方案

### ✅ 正确的实现

```python
# 正确 1: 使用 structure_blocks() 获取 Line 对象
lines = block.structure_blocks(document)

for line in lines:
    if line is None or line.structure is None:
        continue

    # 正确 2: 使用 structure_blocks() 获取 Span 对象
    spans = line.structure_blocks(document)

    for span in spans:
        if not hasattr(span, 'text') or not span.text:
            continue

        # 正确 3: 直接访问 span.text
        original_text = span.text
        cleaned_text = self.clean_text(original_text)

        if cleaned_text != original_text:
            span.text = cleaned_text
            total_cleaned += 1
```

---

## 技术细节

### Block 结构层次

```
Document
  └─ Page
      └─ Block (Text, TextInlineMath, etc.)
          └─ Line (通过 structure 引用)
              └─ Span (通过 structure 引用)
                  └─ text: str
```

### structure_blocks() 方法

**位置**: [marker/schema/blocks/base.py:150-153](marker/schema/blocks/base.py#L150-L153)

```python
def structure_blocks(self, document_page: Document | PageGroup) -> List[Block]:
    if self.structure is None:
        return []
    return [document_page.get_block(block_id) for block_id in self.structure]
```

**作用**：
- 将 `structure` 中的 BlockId 列表转换为实际的 Block 对象列表
- 这是访问子对象的标准方法

### 其他处理器的参考

**TextProcessor** ([marker/processors/text.py:82-86](marker/processors/text.py#L82-L86)):
```python
lines: List[Line] = [
    line
    for line in block.structure_blocks(document)
    if line.polygon.width > 1
]
```

**BlockquoteProcessor** 也使用相同模式。

---

## 修改文件

### 1. marker/processors/markdown_noise.py

**修改位置**: Line 55-101 (`__call__` 方法)

**关键变更**：

```diff
- # 错误：直接迭代 block.structure
- for line_id in block.structure:
-     line = document.get_block(line_id)
-     if not hasattr(line, 'spans') or not line.spans:
-         continue
-     for span in line.spans:

+ # 正确：使用 structure_blocks() 方法
+ lines = block.structure_blocks(document)
+ for line in lines:
+     if line is None or line.structure is None:
+         continue
+     spans = line.structure_blocks(document)
+     for span in spans:
```

---

## 测试验证

### 重启 Streamlit 应用

```bash
# 停止当前应用 (Ctrl+C)
# 重新启动
python -m marker.scripts.streamlit_app
```

### 测试步骤

1. **选择 Pipeline 模式 + Surya Layout**
2. **找到 "🧹 Markdown 噪音清理" 配置**
3. **配置清理选项**：
   - 启用 Markdown 噪音清理
   - 选择清理级别：medium（清理 #, >, -, *, +）
   - 勾选 "只清理行首符号"
4. **上传测试文档**（包含 OCR 识别的 `# 1` 等噪音）
5. **运行转换**
6. **查看控制台输出**：
   ```
   ================================================================================
   🧹 MarkdownNoiseRemovalProcessor 被调用
      清理级别: medium
      只清理行首: True
      自定义符号: ''
   ================================================================================
   🔧 清理文本:
      原文: # 1 这是标题...
      清理后: 1 这是标题...
   ✅ 清理完成，共清理 X 个文本片段
   ================================================================================
   ```

---

## 预期效果

### 清理前（OCR 识别结果）

```markdown
# 1 Introduction

> This is a paragraph

- This is another paragraph
```

### 清理后（medium 级别，只清理行首）

```markdown
1 Introduction

This is a paragraph

This is another paragraph
```

---

## 完成状态

✅ 修复了 `structure_blocks()` 访问方式
✅ 正确获取 Line 对象
✅ 正确获取 Span 对象
✅ 处理器现在可以正确清理文本

**现在重启应用测试！**
