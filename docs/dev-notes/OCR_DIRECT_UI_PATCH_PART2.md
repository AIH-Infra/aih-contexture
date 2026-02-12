# OCR Direct Streamlit UI 集成补丁 - Part 2

## Part 4: 修改 build_config_dict 函数

### 在函数开头添加 OCR Direct 分支

```python
def build_config_dict(config_params: dict) -> dict:
    """构建配置字典"""

    # 🆕 OCR Direct 模式
    conversion_mode = config_params.get("conversion_mode", "traditional")

    if conversion_mode == "ocr_direct":
        # OCR Direct 配置
        cli = {
            "converter_cls": "marker.converters.ocr_direct_async.OcrDirectAsyncConverter",

            # API 配置
            "ocr_endpoint": config_params.get("ocr_endpoint", "http://localhost:1234/v1/chat/completions"),
            "ocr_model": config_params.get("ocr_model", "chandra"),
            "ocr_api_key": config_params.get("ocr_api_key"),
            "ocr_output_format": config_params.get("ocr_output_format", "json"),

            # 并发控制
            "ocr_concurrency": int(config_params.get("ocr_concurrency", 5)),
            "ocr_batch_size": int(config_params.get("ocr_batch_size", 10)),
            "ocr_batch_rest": float(config_params.get("ocr_batch_rest", 2.0)),
            "ocr_max_retries": int(config_params.get("ocr_max_retries", 3)),

            # 图像预处理
            "ocr_resize_max": int(config_params.get("ocr_resize_max", 2048)),
            "ocr_image_format": config_params.get("ocr_image_format", "PNG"),
            "ocr_image_quality": int(config_params.get("ocr_image_quality", 95)),

            # 高级选项
            "ocr_page_anchor_enabled": bool(config_params.get("ocr_page_anchor_enabled", True)),
            "ocr_timeout": int(config_params.get("ocr_timeout", 120)),
            "ocr_max_tokens": int(config_params.get("ocr_max_tokens", 4096)),
            "ocr_temperature": float(config_params.get("ocr_temperature", 0.1)),
        }

        # 页面范围
        if config_params.get("page_range"):
            cli["page_range"] = config_params["page_range"]

        return cli

    # 现有的 traditional 和 vlm_direct 配置
    ocr_backend = config_params.get("ocr_backend", "surya")
    layout_backend = config_params.get("layout_backend", "surya")
    # ... 继续现有代码
```

---

## Part 5: 更新配置参数收集

### 在配置参数收集部分添加（约 Line 1200+）

```python
# 收集配置参数
config_params = {
    "conversion_mode": conversion_mode,  # 🆕 添加转换模式
    "output_dir": st.session_state.output_dir,
    # ... 现有参数
}

# 🆕 OCR Direct 参数
if conversion_mode == "ocr_direct":
    config_params.update({
        "ocr_endpoint": ocr_endpoint,
        "ocr_model": ocr_model,
        "ocr_api_key": ocr_api_key if ocr_api_key else None,
        "ocr_output_format": ocr_output_format,
        "ocr_concurrency": ocr_concurrency,
        "ocr_batch_size": ocr_batch_size,
        "ocr_batch_rest": ocr_batch_rest,
        "ocr_max_retries": ocr_max_retries,
        "ocr_resize_max": ocr_resize_max,
        "ocr_image_format": ocr_image_format,
        "ocr_image_quality": ocr_image_quality,
        "ocr_page_anchor_enabled": ocr_page_anchor_enabled,
        "ocr_timeout": ocr_timeout,
    })
```

---

## Part 6: 更新转换器选择逻辑

### 在转换器实例化部分（约 Line 1300+）

```python
# 根据转换模式选择转换器
if conversion_mode == "vlm_direct":
    from marker.converters.vlm_direct_async import VlmDirectAsyncConverter
    converter = VlmDirectAsyncConverter(config)
elif conversion_mode == "ocr_direct":
    # 🆕 OCR Direct 转换器
    from marker.converters.ocr_direct_async import OcrDirectAsyncConverter
    converter = OcrDirectAsyncConverter(config)
else:
    # traditional 模式
    from marker.converters.pdf import PdfConverter
    converter = PdfConverter(config)
```

---

## 集成检查清单

- [ ] Part 1: 修改转换模式选择
- [ ] Part 2: 添加模式说明
- [ ] Part 3: 添加配置界面
- [ ] Part 4: 修改 build_config_dict
- [ ] Part 5: 更新参数收集
- [ ] Part 6: 更新转换器选择

完成后测试：
1. UI 显示正常
2. 配置参数正确传递
3. 转换器正确实例化
4. 端到端转换成功
