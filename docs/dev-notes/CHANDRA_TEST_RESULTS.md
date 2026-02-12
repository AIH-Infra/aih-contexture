# Chandra OCR 测试结果分析

## ✅ 测试成功！

测试日期：2026-02-04
测试图片：德文古籍页面（Rudolf Haym, 1885）

---

## 📊 关键发现

### 1. JSON 输出能力

**结果**：✅ **Chandra 支持 JSON 输出**

**输出质量**：
- JSON 结构完整
- 包含所有必需字段
- 只有微小的格式问题（缺少一个 `type` 字段）

**示例输出**：
```json
{
  "blocks": [
    {
      "text": "Entstehung der Theologischen Briefe. 127",
      "bbox": [286, 63, 650, 80],
      "type": "page header"
    },
    {
      "text": "und Beruf war? wenn er...",
      "bbox": [25, 96, 921, 138]
    }
  ]
}
```

---

### 2. 坐标信息

**结果**：✅ **完整的 bbox 坐标**

**格式**：`[x1, y1, x2, y2]`

**示例**：
- 页眉：`[286, 63, 650, 80]`
- 正文段落：`[25, 143, 921, 716]`
- 脚注：`[25, 749, 918, 819]`

---

### 3. 块类型识别

**结果**：✅ **可以识别块类型**

**识别的类型**：
- `"page header"` - 页眉
- 正文段落（未标注类型，默认为 text）
- 脚注（通过上标符号识别）

---

### 4. OCR 准确度

**结果**：✅ **极高的准确度**

**测试内容**：
- ✅ 德文特殊字符（ä, ö, ü, ß）
- ✅ 上标符号（¹, ², ³, ⁴, ⁵）
- ✅ 引号（„ "）
- ✅ 复杂排版（脚注、长段落）

**示例**：
```
原文：„Alles, was Candidat ist," klagt er...
识别：„Alles, was Candidat ist," klagt er...
准确度：100%
```

---

## 🎯 关键结论

### 对 Marker 集成的影响

1. **✅ 可以使用 JSON 格式**
   - 通过 prompt 引导即可
   - 结构稳定，易于解析

2. **✅ 坐标信息完整**
   - 每个块都有 bbox
   - 可以直接转换为 PolygonBox

3. **✅ 块类型可识别**
   - 虽然不是所有块都有 type
   - 可以通过启发式规则补充

4. **✅ OCR 质量优秀**
   - 特别适合德文古籍
   - 上标、特殊字符识别完美

---

## 📋 推荐的实现方案

### 方案：使用 JSON 格式作为主要输出

**Prompt 模板**：
```python
prompt = """Extract all text from this image and output as JSON with this structure:
{
  "blocks": [
    {
      "text": "extracted text",
      "bbox": [x1, y1, x2, y2],
      "type": "text|title|table|figure|equation"
    }
  ]
}

Include bbox coordinates for every block.
Identify block types: text, title, table, figure, equation, page_header, page_footer.
"""
```

**解析策略**：
1. 解析 JSON
2. 提取 blocks 数组
3. 为每个 block 创建 Marker 的 Block 对象
4. 使用 bbox 创建 PolygonBox
5. 映射 type 到 BlockTypes

---

