# 印刷页码修复 - 快速总结

## 根本原因

**PageNumberProcessor 从未被执行！**

原因：
- ❌ 未导入到 pdf.py
- ❌ 未添加到 default_processors 列表

## 修复内容

**文件**: marker/converters/pdf.py

### 1. 添加导入
```python
from marker.processors.page_number import PageNumberProcessor
```

### 2. 添加到处理器列表
```python
default_processors: Tuple[BaseProcessor, ...] = (
    # ...
    PageHeaderProcessor,
    PageNumberProcessor,  # ← 新添加
    SectionHeaderProcessor,
    # ...
)
```

## 现在可以工作

```markdown
{0}

<!-- Page: XII -->  ← 现在会显示！
前言内容...

{1}

<!-- Page: 1 -->  ← 现在会显示！
第一章内容...
```

## 测试

```bash
cd d:\marker_cuda
streamlit run marker\scripts\streamlit_app.py
```

配置：
- Pipeline 模式
- Surya 布局
- 启用 PDF 文本层（或 OCR）
- 启用"提取印刷页码"

## 详细文档

查看: [PAGE_NUMBER_ROOT_CAUSE.md](PAGE_NUMBER_ROOT_CAUSE.md)

---

**修复完成！印刷页码现在可以正常提取！** ✓
