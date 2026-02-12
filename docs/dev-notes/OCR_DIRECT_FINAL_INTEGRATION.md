# OCR Direct 最终集成方案

## ✅ 关键决策：保持现有参数名

经过深度分析，我们决定**保持现有参数名**，原因：

1. **上下文隔离**：Pipeline 和 OCR Direct 通过 `converter_cls` 分离
2. **配置清晰**：在 Streamlit UI 中通过不同的配置面板隔离
3. **代码简洁**：避免不必要的重命名

## 📋 集成策略

### 1. Streamlit UI 结构

```python
# 顶层：转换模式选择
conversion_mode = st.radio(
    "转换模式",
    options=["pipeline", "ocr_direct"],
    format_func=lambda x: {
        "pipeline": "🔄 Pipeline (传统模式)",
        "ocr_direct": "📚 OCR Direct (专业 OCR)"
    }[x]
)

if conversion_mode == "pipeline":
    # 现有的 Pipeline 配置
    ocr_backend = st.selectbox("OCR 后端", ...)
    layout_backend = st.selectbox("版面识别后端", ...)
    ...

elif conversion_mode == "ocr_direct":
    # OCR Direct 配置
    ocr_endpoint = st.text_input("API Endpoint", ...)
    ocr_model = st.text_input("模型名称", ...)
    ocr_concurrency = st.number_input("并发数", ...)
    ...
```

### 2. build_config_dict 集成

```python
def build_config_dict(config_params: dict) -> dict:
    conversion_mode = config_params.get("conversion_mode", "pipeline")

    if conversion_mode == "ocr_direct":
        # OCR Direct 配置
        return {
            "converter_cls": "marker.converters.ocr_direct_async.OcrDirectAsyncConverter",
            "ocr_endpoint": config_params.get("ocr_endpoint"),
            "ocr_model": config_params.get("ocr_model"),
            "ocr_output_format": config_params.get("ocr_output_format"),
            "ocr_concurrency": config_params.get("ocr_concurrency"),
            "ocr_batch_size": config_params.get("ocr_batch_size"),
            # ... 其他 OCR Direct 参数
        }

    # 现有 Pipeline 配置
    ocr_backend = config_params.get("ocr_backend", "surya")
    ...
```

## 🎯 实施步骤

### Step 1: 创建 Streamlit UI 配置面板
- [ ] 添加转换模式选择
- [ ] 添加 OCR Direct 配置界面
- [ ] 测试 UI 交互

### Step 2: 集成 build_config_dict
- [ ] 添加 OCR Direct 分支
- [ ] 测试配置生成

### Step 3: 端到端测试
- [ ] Pipeline 模式测试
- [ ] OCR Direct 模式测试
- [ ] 切换测试

## ✅ 优势

1. **无参数冲突**：通过上下文隔离
2. **代码简洁**：无需重命名
3. **易于维护**：清晰的分支逻辑
4. **用户友好**：直观的 UI 选择

准备开始实施！
