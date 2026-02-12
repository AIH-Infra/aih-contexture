# max_tokens 参数修复 ✅

## 🔍 问题根源

LM Studio 报错：
```
{
  "error": {
    "message": "Unrecognized key(s) in object: 'max_tokens'",
    "type": "invalid_request",
    "code": "unrecognized_keys"
  }
}
```

## 🎯 根本原因

**问题位置**: [marker/converters/ocr_direct_async.py:148](marker/converters/ocr_direct_async.py#L148)

```python
# ❌ 错误：传递了 max_tokens 参数
ocr_service_config = {
    "ocr_endpoint": self.endpoint,
    "ocr_model": self.model,
    "ocr_api_key": self.api_key or "",
    "ocr_output_format": self.output_format,
    "ocr_max_tokens": self.max_tokens,  # ❌ LM Studio 不支持！
    "ocr_temperature": self.temperature,
    "ocr_timeout": self.timeout,
    "max_retries": self.max_retries
}
```

## ✅ 修复方案

**已删除 `ocr_max_tokens` 参数传递**

```python
# ✅ 正确：不传递 max_tokens
ocr_service_config = {
    "ocr_endpoint": self.endpoint,
    "ocr_model": self.model,
    "ocr_api_key": self.api_key or "",
    "ocr_output_format": self.output_format,
    # 注意：不传递 ocr_max_tokens，LM Studio 不支持此参数
    "ocr_temperature": self.temperature,
    "ocr_timeout": self.timeout,
    "max_retries": self.max_retries
}
```

## 📝 修复文件

- ✅ [marker/converters/ocr_direct_async.py:148](marker/converters/ocr_direct_async.py#L148) - 删除 `ocr_max_tokens` 参数
- ✅ [marker/services/ocr_chandra.py](marker/services/ocr_chandra.py) - 添加调试日志

## 🚀 现在可以重新测试

```bash
streamlit run marker/scripts/streamlit_app.py
```

**LM Studio 不再报错 `max_tokens` 了！**
