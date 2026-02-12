# Chandra 结构化输出测试指南

## 📋 测试目的

验证 Chandra 是否支持强制结构化 JSON 输出，以便在 Marker 中更好地解析其输出。

---

## 🧪 测试文件

### 1. JSON Schema 定义
**文件**: `test_chandra_json_schemas.json`

包含 3 个测试 schema：
- `basic_ocr`: 基础结构（文本+坐标+类型）
- `detailed_ocr`: 详细结构（包含置信度、格式化信息）
- `hierarchical_ocr`: 层次结构（块→行→词）

### 2. 完整测试脚本
**文件**: `test_chandra_structured_output.py`

使用 `response_format` 参数强制 JSON Schema 输出（OpenAI 兼容）

### 3. 简化测试脚本
**文件**: `test_chandra_simple.py`

通过 prompt 引导输出 JSON（不依赖 response_format）

---

## 🚀 使用步骤

### 步骤 1: 准备测试图片

选择一张包含文本的图片（建议使用你之前测试的德文古籍页面）

### 步骤 2: 修改配置

编辑测试脚本，修改这一行：
```python
TEST_IMAGE_PATH = "path/to/your/test/image.png"
```

改为你的图片路径，例如：
```python
TEST_IMAGE_PATH = "D:/test_images/german_book_page.png"
```

### 步骤 3: 运行测试

**先运行简化版**（推荐）：
```bash
python test_chandra_simple.py
```

**如果成功，再运行完整版**：
```bash
python test_chandra_structured_output.py
```

---

## 📊 预期结果

### 场景 A: 支持结构化输出

```
✅ 成功返回 JSON
✅ 完整输出已保存: chandra_output_test1_basic.json
```

**输出示例**：
```json
{
  "blocks": [
    {
      "text": "Enthusiasmus für Kant.",
      "bbox": [365, 48, 579, 63],
      "type": "title"
    },
    {
      "text": "jünger Theolog zu hören...",
      "bbox": [72, 77, 160, 95],
      "type": "text"
    }
  ]
}
```

### 场景 B: 不支持结构化输出

```
❌ 返回的不是有效 JSON
原始输出已保存: chandra_output_test1_basic.txt
```

**输出可能是 HTML 或 Markdown**

---

## 🔍 分析输出

### 如果返回 JSON

✅ **好消息**！Chandra 支持结构化输出

**下一步**：
1. 查看输出的 JSON 结构
2. 确定最适合的 schema
3. 开始实现 OCR Direct 模式

### 如果返回 HTML/Markdown

⚠️ **需要解析**

**下一步**：
1. 使用 BeautifulSoup 解析 HTML
2. 或使用正则表达式解析 Markdown
3. 提取文本和坐标信息

---

## 📝 测试后提供给我

运行测试后，请提供：

1. **测试结果**：
   - 哪些测试成功了？
   - 哪些测试失败了？

2. **输出文件**：
   - `chandra_output_*.json` 或 `chandra_output_*.txt`
   - 至少提供一个完整的输出示例

3. **LM Studio 日志**：
   - 是否有错误信息？
   - 处理时间如何？

---

## 💡 提示

### 如果 LM Studio 报错

可能的原因：
- 不支持 `response_format` 参数
- 不支持 `json_schema` 类型

**解决方案**：使用简化版测试脚本

### 如果输出不稳定

尝试调整参数：
```python
"temperature": 0.0,  # 降低到 0
"max_tokens": 8192,  # 增加 token 限制
```

---

## 🎯 关键问题

测试要回答的核心问题：

1. ✅ Chandra 能否输出 JSON？
2. ✅ JSON 结构是否包含坐标？
3. ✅ JSON 结构是否包含块类型？
4. ✅ 是否需要特殊 prompt？
5. ✅ 输出是否稳定一致？

准备好后运行测试，然后把结果告诉我！
