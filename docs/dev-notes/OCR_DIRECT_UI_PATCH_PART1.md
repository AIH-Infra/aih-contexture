# OCR Direct Streamlit UI 集成补丁

## Part 1: 修改转换模式选择（Line 460）

### 原代码
```python
conversion_mode = st.radio(
    "选择转换模式",
    options=["traditional", "vlm_direct"],
    index=0,
    format_func=lambda x: {
        "traditional": "🔧 传统模式（Marker Pipeline）",
        "vlm_direct": "🚀 VLM Direct 模式（纯 VLM 异步并发）",
    }.get(x, x),
    horizontal=True,
    help="传统模式使用 Marker 的完整 pipeline（Layout + OCR），VLM Direct 模式完全跳过 Surya，纯用 VLM 异步并发处理"
)
```

### 修改为
```python
conversion_mode = st.radio(
    "选择转换模式",
    options=["traditional", "vlm_direct", "ocr_direct"],
    index=0,
    format_func=lambda x: {
        "traditional": "🔧 传统模式（Marker Pipeline）",
        "vlm_direct": "🚀 VLM Direct 模式（纯 VLM 异步并发）",
        "ocr_direct": "📚 OCR Direct 模式（专业 OCR）",
    }.get(x, x),
    horizontal=True,
    help="传统模式使用 Marker 的完整 pipeline，VLM Direct 模式纯用 VLM 处理，OCR Direct 模式使用专业 OCR 引擎（如 Chandra）"
)
```

---

## Part 2: 添加 OCR Direct 模式说明（Line 472 后）

### 在现有的 if-else 后添加
```python
elif conversion_mode == "ocr_direct":
    st.info(
        "📚 **OCR Direct 模式**\n\n"
        "- ✅ 使用专业 OCR 引擎（Chandra）\n"
        "- ✅ 异步并发处理\n"
        "- ✅ 支持手写、表格、公式\n"
        "- ✅ 保留坐标信息\n"
        "- ✅ 批处理与休息间隔\n\n"
        "**适用场景**：手写文档、复杂表格、数学公式、古籍文献"
    )
```

---

## Part 3: 添加 OCR Direct 配置界面

### 在 traditional 模式配置后添加（约 Line 800+）

```python
# ==================== OCR Direct 模式配置 ====================
if conversion_mode == "ocr_direct":
    st.divider()
    st.subheader("📚 OCR Direct 配置")

    # API 配置
    with st.expander("🔌 API 配置", expanded=True):
        ocr_endpoint = st.text_input(
            "API Endpoint",
            value="http://localhost:1234/v1/chat/completions",
            help="OCR API 端点（OpenAI 兼容）"
        )

        ocr_model = st.text_input(
            "模型名称",
            value="chandra",
            help="OCR 模型名称"
        )

        ocr_api_key = st.text_input(
            "API Key（可选）",
            value="",
            type="password",
            help="如果 API 需要认证"
        )

        ocr_output_format = st.selectbox(
            "输出格式",
            options=["json", "html", "markdown"],
            index=0,
            help="JSON 格式包含坐标信息（推荐）"
        )

    # 并发控制
    with st.expander("⚡ 并发控制", expanded=True):
        col1, col2 = st.columns(2)

        with col1:
            ocr_concurrency = st.number_input(
                "最大并发数",
                min_value=1,
                max_value=20,
                value=5,
                help="同时处理的页面数"
            )

            ocr_batch_size = st.number_input(
                "批次大小",
                min_value=1,
                max_value=50,
                value=10,
                help="每批处理的页面数"
            )

        with col2:
            ocr_batch_rest = st.number_input(
                "批次休息时间（秒）",
                min_value=0.0,
                max_value=10.0,
                value=2.0,
                step=0.5,
                help="批次间的休息时间"
            )

            ocr_max_retries = st.number_input(
                "最大重试次数",
                min_value=1,
                max_value=10,
                value=3,
                help="API 调用失败时的重试次数"
            )

    # 图像预处理
    with st.expander("🖼️ 图像预处理", expanded=False):
        col1, col2 = st.columns(2)

        with col1:
            ocr_resize_max = st.number_input(
                "最大图像尺寸",
                min_value=512,
                max_value=4096,
                value=2048,
                step=256,
                help="图像最大边长（像素）"
            )

            ocr_image_format = st.selectbox(
                "图像格式",
                options=["PNG", "JPEG"],
                index=0,
                help="发送给 API 的图像格式"
            )

        with col2:
            if ocr_image_format == "JPEG":
                ocr_image_quality = st.slider(
                    "JPEG 质量",
                    min_value=50,
                    max_value=100,
                    value=95,
                    help="JPEG 压缩质量"
                )
            else:
                ocr_image_quality = 95

    # 高级选项
    with st.expander("⚙️ 高级选项", expanded=False):
        ocr_page_anchor_enabled = st.checkbox(
            "启用页码锚点",
            value=True,
            help="在输出中添加页码锚点 {n}"
        )

        ocr_timeout = st.number_input(
            "API 超时时间（秒）",
            min_value=30,
            max_value=300,
            value=120,
            help="单个 API 请求的超时时间"
        )
```

文件已保存。接下来我会创建 Part 4...
