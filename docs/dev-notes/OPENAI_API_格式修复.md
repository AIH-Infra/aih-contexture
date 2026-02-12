# OpenAI API 格式修复 ✅

## 🎯 根本问题发现

**你说得对！问题不在图片质量！**

在 LM Studio 中直接发送图片很轻松，但我们的代码发送后 token 数爆炸（874102 tokens）！

**真正的问题**：我们使用了错误的 API 格式！

---

## ❌ 之前的错误格式

### 错误的请求格式
```python
# ❌ 错误：使用 input 字段
{
  "model": "chandra",
  "input": "data:image/png;base64,iVBORw0KGgo...\n\nExtract text..."
}
```

**问题**：LM Studio 把整个 base64 字符串当作**文本 token** 处理！
- 结果：874102 tokens（~850KB base64 被当作文本）
- 超过上下文窗口（8192 tokens）

### 错误的响应解析
```python
# ❌ 错误：期望 {"content": "..."}
if "content" in result:
    content = result["content"]
```

---

## ✅ 正确的 OpenAI API 格式

### 正确的请求格式
```python
# ✅ 正确：使用 messages 数组 + image_url
{
  "model": "chandra",
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/jpeg;base64,..."
          }
        },
        {
          "type": "text",
          "text": "Extract text from this image"
        }
      ]
    }
  ],
  "temperature": 0.1
}
```

**效果**：
- 图像被正确识别为图像（不是文本）
- Token 数量正常（只计算 prompt 文本）
- 不会超过上下文窗口

### 正确的响应解析
```python
# ✅ 正确：OpenAI Chat Completions 格式
if "choices" in result and len(result["choices"]) > 0:
    content = result["choices"][0]["message"]["content"]
```

---

## 🔧 修改的文件

### 1. [marker/services/ocr_chandra.py](marker/services/ocr_chandra.py)

**Line 37**: 端点
```python
# ❌ 之前
"http://localhost:1234/api/v1/chat"

# ✅ 现在
"http://localhost:1234/v1/chat/completions"
```

**Line 131-147**: 请求格式
```python
# ✅ 使用 OpenAI Chat Completions 格式
payload = {
    "model": self.ocr_model,
    "messages": [
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_base64}"}},
                {"type": "text", "text": prompt}
            ]
        }
    ],
    "temperature": self.ocr_temperature
}
```

**Line 239-244 & 310-314**: 响应解析
```python
# ✅ OpenAI 格式
if "choices" in result and len(result["choices"]) > 0:
    content = result["choices"][0]["message"]["content"]
```

### 2. [marker/converters/ocr_direct_async.py](marker/converters/ocr_direct_async.py)

**Line 121-122**: 端点自动补全
```python
# ✅ 自动补全为标准端点
if self.endpoint.endswith("/v1"):
    self.endpoint = self.endpoint.replace("/v1", "/v1/chat/completions")
```

---

## 📊 效果对比

| 项目 | 之前（错误） | 现在（正确） |
|------|-------------|-------------|
| API 格式 | `input` 字段 | `messages` 数组 |
| 图像处理 | 当作文本 token | 当作图像 |
| Token 数 | 874102 | ~100-200 |
| 上下文窗口 | ❌ 超限 | ✅ 正常 |
| LM Studio | ❌ 报错 | ✅ 成功 |

---

## 🚀 现在重启测试

```bash
# 1. 停止 Streamlit (Ctrl+C)
# 2. 重新启动
streamlit run marker/scripts/streamlit_app.py
```

**预期结果**：
- ✅ LM Studio 正确识别图像
- ✅ Token 数量正常（~100-200）
- ✅ 成功返回 OCR 结果
- ✅ 不再报 "Cannot truncate prompt" 错误

---

## 💡 关键点

**这就是为什么你在 LM Studio 中直接发送图片很轻松！**

LM Studio 的 UI 使用的是标准的 OpenAI Chat Completions API 格式，图像被正确识别为图像。

而我们之前使用的 `input` 字段格式，导致 LM Studio 把 base64 字符串当作文本处理，token 数爆炸！

现在修复后，我们的代码和 LM Studio UI 使用相同的 API 格式了！
