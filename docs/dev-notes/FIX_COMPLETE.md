# 错误修复完成 - 快速指南

## 问题

```
TypeError: PageAnchorFormatter.__init__() got an unexpected keyword argument 'template'
```

## 已修复

✅ 移除了 MarkdownRenderer 中的旧参数
✅ 更新为新的简化 API

## 修复内容

### 文件：[marker/renderers/markdown.py](marker/renderers/markdown.py)

**移除的代码**：
```python
# 旧的类属性（已删除）
page_anchor_template: Annotated[str, "..."] = "{n}"
page_anchor_start: Annotated[int, "..."] = 0
```

**更新的代码**：
```python
# 旧代码
formatter = PageAnchorFormatter(
    template=self.page_anchor_template,
    page_anchor_start=self.page_anchor_start
)

# 新代码
formatter = PageAnchorFormatter(wrapper="{{{}}}")
```

## 现在可以正常使用

重新运行你的 PDF 转换，错误应该已经解决。

## 关于 Surya + OCR 的问题

### 简短回答

**❌ Surya + 禁用 OCR 无法识别印刷页码**

原因：
- Surya 只检测**位置**（页眉/页脚在哪里）
- OCR 才能读取**内容**（页码是什么）
- 印刷页码识别需要文本内容

### 解决方案

#### 方案 1: 启用 OCR（扫描件）

```python
config = {
    "layout_backend": "surya",
    "ocr_engine": "surya_ocr",  # ✅ 启用 OCR
    "use_printed_page_number": True,
}
```

#### 方案 2: 使用 PDF 文本层（电子文档）

```python
config = {
    "layout_backend": "surya",
    "ocr_engine": "none",
    "use_pdf_text": True,  # ✅ 使用 PDF 内嵌文本
    "use_printed_page_number": True,
}
```

#### 方案 3: 自定义编号（无法识别时）

```python
config = {
    "layout_backend": "surya",
    "ocr_engine": "none",
    "use_printed_page_number": False,
    "custom_id_source": "auto",  # ✅ 使用自定义编号
    "custom_id_data": {
        "prefix": "page",
        "start": 1,
        "digits": 3
    }
}
```

## 详细说明

请查看：[SURYA_OCR_PAGE_NUMBER_GUIDE.md](SURYA_OCR_PAGE_NUMBER_GUIDE.md)

## 测试

运行以下命令测试修复：

```bash
cd d:\marker_cuda
python -m py_compile marker\renderers\markdown.py
```

应该没有错误输出。

## 相关文档

- [SURYA_OCR_PAGE_NUMBER_GUIDE.md](SURYA_OCR_PAGE_NUMBER_GUIDE.md) - Surya + OCR 详细说明
- [PIPELINE_VERIFICATION_REPORT.md](PIPELINE_VERIFICATION_REPORT.md) - Pipeline 验证报告
- [UI_UPDATE_COMPLETE.md](UI_UPDATE_COMPLETE.md) - UI 更新完整报告
