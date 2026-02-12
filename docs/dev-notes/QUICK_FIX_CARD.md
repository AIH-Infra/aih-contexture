# 快速修复参考卡

## 🎯 问题已解决

✅ 变量名映射错误 → 已修复
✅ 双层括号问题 → 已修复
✅ 所有测试通过 → 可以使用

---

## 📋 推荐配置

### 电子 PDF（有文本层）
```python
{
    "layout_backend": "surya",
    "ocr_engine": "none",
    "use_pdf_text": True,  # ← 关键
    "use_printed_page_number": True,
}
```

### 扫描件 PDF（无文本层）
```python
{
    "layout_backend": "surya",
    "ocr_engine": "surya_ocr",  # ← 关键
    "use_printed_page_number": True,
}
```

---

## ✅ 正确输出格式

```markdown
{0}

<!-- Page: XII -->
前言内容...

{1}

<!-- Page: 1 -->
第一章内容...

{2}  ← 文档末尾额外锚点
```

---

## ⚠️ 重要提醒

**Surya ≠ OCR**
- Surya：检测位置（WHERE）
- OCR：读取内容（WHAT）
- 印刷页码需要文本内容

**禁用 OCR 的正确方式**
- ✅ 有文本层：`use_pdf_text=True`
- ❌ 完全禁用：无法识别页码

---

## 📄 详细文档

- [FINAL_FIX_SUMMARY.md](FINAL_FIX_SUMMARY.md) - 完整总结
- [DOUBLE_FIX_REPORT.md](DOUBLE_FIX_REPORT.md) - 详细报告
- [SURYA_OCR_PAGE_NUMBER_GUIDE.md](SURYA_OCR_PAGE_NUMBER_GUIDE.md) - 完整指南

---

## 🚀 立即测试

```bash
cd d:\marker_cuda
python test_double_fix.py
```

预期结果：所有测试通过 ✅

---

**修复完成，可以正常使用！** 🎉
