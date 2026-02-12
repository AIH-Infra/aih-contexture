"""
直接修改 Line 1295 的 else: 为 elif conversion_mode == "ocr_direct":
"""
from pathlib import Path

streamlit_file = Path("marker/scripts/streamlit_app.py")

print("Reading file...")
lines = streamlit_file.read_text(encoding='utf-8').split('\n')

print(f"Line 1295 current: {repr(lines[1294])}")

# 直接修改 Line 1295
if lines[1294].strip() == "else:":
    lines[1294] = '    elif conversion_mode == "ocr_direct":'
    print("[OK] Modified Line 1295 to elif")

    # 在 Line 1295 后插入 OCR Direct 配置
    ocr_config_lines = [
        '        # ==================== OCR Direct Mode Config ====================',
        '        st.subheader("OCR Direct Config")',
        '',
        '        # API Config',
        '        with st.expander("API Config", expanded=True):',
        '            ocr_endpoint = st.text_input(',
        '                "API Endpoint",',
        '                value="http://localhost:1234/v1/chat/completions",',
        '                help="OCR API endpoint (OpenAI compatible)",',
        '                key="ocr_endpoint"',
        '            )',
        '            ocr_model = st.text_input(',
        '                "Model Name",',
        '                value="chandra",',
        '                help="OCR model name",',
        '                key="ocr_model"',
        '            )',
        '            ocr_api_key = st.text_input(',
        '                "API Key (optional)",',
        '                value="",',
        '                type="password",',
        '                help="If API requires authentication",',
        '                key="ocr_api_key"',
        '            )',
        '            ocr_output_format = st.selectbox(',
        '                "Output Format",',
        '                options=["json", "html", "markdown"],',
        '                index=0,',
        '                help="JSON format includes coordinate info (recommended)",',
        '                key="ocr_output_format"',
        '            )',
        '',
        '        # Concurrency Control',
        '        with st.expander("Concurrency Control", expanded=True):',
        '            col1, col2 = st.columns(2)',
        '            with col1:',
        '                ocr_concurrency = st.number_input(',
        '                    "Max Concurrency",',
        '                    min_value=1,',
        '                    max_value=20,',
        '                    value=5,',
        '                    help="Number of pages to process simultaneously",',
        '                    key="ocr_concurrency"',
        '                )',
        '                ocr_batch_size = st.number_input(',
        '                    "Batch Size",',
        '                    min_value=1,',
        '                    max_value=50,',
        '                    value=10,',
        '                    help="Pages per batch",',
        '                    key="ocr_batch_size"',
        '                )',
        '            with col2:',
        '                ocr_batch_rest = st.number_input(',
        '                    "Batch Rest Time (seconds)",',
        '                    min_value=0.0,',
        '                    max_value=10.0,',
        '                    value=2.0,',
        '                    step=0.5,',
        '                    help="Rest time between batches",',
        '                    key="ocr_batch_rest"',
        '                )',
        '                ocr_max_retries = st.number_input(',
        '                    "Max Retries",',
        '                    min_value=1,',
        '                    max_value=10,',
        '                    value=3,',
        '                    help="Retry count on API failure",',
        '                    key="ocr_max_retries"',
        '                )',
        '',
        '        # Image Preprocessing',
        '        with st.expander("Image Preprocessing", expanded=False):',
        '            col1, col2 = st.columns(2)',
        '            with col1:',
        '                ocr_resize_max = st.number_input(',
        '                    "Max Image Size",',
        '                    min_value=512,',
        '                    max_value=4096,',
        '                    value=2048,',
        '                    step=256,',
        '                    help="Max image dimension (pixels)",',
        '                    key="ocr_resize_max"',
        '                )',
        '                ocr_image_format = st.selectbox(',
        '                    "Image Format",',
        '                    options=["PNG", "JPEG"],',
        '                    index=0,',
        '                    help="Image format sent to API",',
        '                    key="ocr_image_format"',
        '                )',
        '            with col2:',
        '                if ocr_image_format == "JPEG":',
        '                    ocr_image_quality = st.slider(',
        '                        "JPEG Quality",',
        '                        min_value=50,',
        '                        max_value=100,',
        '                        value=95,',
        '                        help="JPEG compression quality",',
        '                        key="ocr_image_quality"',
        '                    )',
        '                else:',
        '                    ocr_image_quality = 95',
        '',
        '        # Advanced Options',
        '        with st.expander("Advanced Options", expanded=False):',
        '            ocr_page_anchor_enabled = st.checkbox(',
        '                "Enable Page Anchors",',
        '                value=True,',
        '                help="Add page anchors {n} in output",',
        '                key="ocr_page_anchor_enabled"',
        '            )',
        '            ocr_timeout = st.number_input(',
        '                "API Timeout (seconds)",',
        '                min_value=30,',
        '                max_value=300,',
        '                value=120,',
        '                help="Timeout for single API request",',
        '                key="ocr_timeout"',
        '            )',
        '',
        '    else:',
    ]

    # 在 Line 1295 后插入配置代码
    lines = lines[:1295] + ocr_config_lines + lines[1295:]

    print(f"[OK] Inserted {len(ocr_config_lines)} lines of OCR Direct config")

    # 保存文件
    streamlit_file.write_text('\n'.join(lines), encoding='utf-8')
    print("[SUCCESS] File saved!")

else:
    print(f"[ERROR] Line 1295 is not 'else:', it is: {repr(lines[1294])}")
