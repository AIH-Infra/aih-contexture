"""
OCR Direct 配置界面代码

将此代码插入到 streamlit_app.py 的 Line 1142
在 elif conversion_mode == "ocr_direct": 之后
"""

OCR_DIRECT_CONFIG_CODE = '''
    elif conversion_mode == "ocr_direct":
        # ==================== OCR Direct 模式配置 ====================
        st.subheader("📚 OCR Direct 配置")

        # API 配置
        with st.expander("🔌 API 配置", expanded=True):
            ocr_endpoint = st.text_input(
                "API Endpoint",
                value="http://localhost:1234/v1/chat/completions",
                help="OCR API 端点（OpenAI 兼容）",
                key="ocr_endpoint"
            )

            ocr_model = st.text_input(
                "模型名称",
                value="chandra",
                help="OCR 模型名称",
                key="ocr_model"
            )

            ocr_api_key = st.text_input(
                "API Key（可选）",
                value="",
                type="password",
                help="如果 API 需要认证",
                key="ocr_api_key"
            )

            ocr_output_format = st.selectbox(
                "输出格式",
                options=["json", "html", "markdown"],
                index=0,
                help="JSON 格式包含坐标信息（推荐）",
                key="ocr_output_format"
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
                    help="同时处理的页面数",
                    key="ocr_concurrency"
                )

                ocr_batch_size = st.number_input(
                    "批次大小",
                    min_value=1,
                    max_value=50,
                    value=10,
                    help="每批处理的页面数",
                    key="ocr_batch_size"
                )

            with col2:
                ocr_batch_rest = st.number_input(
                    "批次休息时间（秒）",
                    min_value=0.0,
                    max_value=10.0,
                    value=2.0,
                    step=0.5,
                    help="批次间的休息时间",
                    key="ocr_batch_rest"
                )

                ocr_max_retries = st.number_input(
                    "最大重试次数",
                    min_value=1,
                    max_value=10,
                    value=3,
                    help="API 调用失败时的重试次数",
                    key="ocr_max_retries"
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
                    help="图像最大边长（像素）",
                    key="ocr_resize_max"
                )

                ocr_image_format = st.selectbox(
                    "图像格式",
                    options=["PNG", "JPEG"],
                    index=0,
                    help="发送给 API 的图像格式",
                    key="ocr_image_format"
                )

            with col2:
                if ocr_image_format == "JPEG":
                    ocr_image_quality = st.slider(
                        "JPEG 质量",
                        min_value=50,
                        max_value=100,
                        value=95,
                        help="JPEG 压缩质量",
                        key="ocr_image_quality"
                    )
                else:
                    ocr_image_quality = 95

        # 高级选项
        with st.expander("⚙️ 高级选项", expanded=False):
            ocr_page_anchor_enabled = st.checkbox(
                "启用页码锚点",
                value=True,
                help="在输出中添加页码锚点 {n}",
                key="ocr_page_anchor_enabled"
            )

            ocr_timeout = st.number_input(
                "API 超时时间（秒）",
                min_value=30,
                max_value=300,
                value=120,
                help="单个 API 请求的超时时间",
                key="ocr_timeout"
            )
'''

if __name__ == "__main__":
    print("=" * 80)
    print("OCR Direct 配置界面代码")
    print("=" * 80)
    print("\n将以下代码插入到 streamlit_app.py 的 Line 1142")
    print("在 'elif conversion_mode == \"ocr_direct\":' 之后\n")
    print(OCR_DIRECT_CONFIG_CODE)
    print("\n" + "=" * 80)
