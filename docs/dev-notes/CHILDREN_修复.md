# PageGroup children 修复 ✅

## 🎯 问题

```python
TypeError: 'NoneType' object is not iterable
[str(block.block_type) for block in page.children]
                                    ^^^^^^^^^^^^^
```

**原因**：`PageGroup.children` 是 `None`

---

## ✅ 修复

**文件**: [marker/builders/ocr_parser.py](marker/builders/ocr_parser.py)

```python
# ❌ 之前：使用 structure（错误）
page = PageGroup(
    page_id=page_id,
    polygon=page_polygon,
    structure=blocks  # 错误：structure 需要 BlockId 列表
)

# ✅ 现在：使用 children（正确）
page = PageGroup(
    page_id=page_id,
    polygon=page_polygon,
    children=blocks  # 正确：children 存储 Block 对象列表
)
```

---

## 📊 进展总结

1. ✅ **max_tokens 参数** - 已删除
2. ✅ **API 格式** - 改为 OpenAI Chat Completions
3. ✅ **Token 数量** - 从 874102 降到 1647
4. ✅ **OCR 成功** - LM Studio 正常返回结果
5. ✅ **children 属性** - 修复 PageGroup 创建

---

## 🚀 重启测试

```bash
streamlit run marker/scripts/streamlit_app.py
```

现在应该能完整转换了！
