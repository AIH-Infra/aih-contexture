"""
重新组织 OCR Direct 配置界面
1. 将并发控制整合进高级选项
2. 移除启用页码锚点复选框
"""
from pathlib import Path

streamlit_file = Path("marker/scripts/streamlit_app.py")

print("Step 1: Reading file...")
lines = streamlit_file.read_text(encoding='utf-8').split('\n')

print("\nStep 2: Finding OCR Direct config section...")

# 找到 OCR Direct 配置的开始和结束位置
start_idx = None
end_idx = None

for i, line in enumerate(lines):
    if 'elif conversion_mode == "ocr_direct":' in line:
        start_idx = i
        print(f"[OK] Found OCR Direct config start at line {i+1}")
    if start_idx and '    else:' in line and i > start_idx + 100:
        end_idx = i
        print(f"[OK] Found OCR Direct config end at line {i+1}")
        break

if not start_idx or not end_idx:
    print("[ERROR] Could not find OCR Direct config boundaries")
    exit(1)

print(f"\n[INFO] OCR Direct config: lines {start_idx+1} to {end_idx}")

# 构建新的配置界面
new_config = [
    '    elif conversion_mode == "ocr_direct":',
    '        # ==================== OCR Direct 模式配置 ====================',
    '        st.subheader("📚 OCR Direct 配置")',
    '',
    '        # API 配置',
    '        with st.expander("🔌 API 配置", expanded=True):',
    '            ocr_endpoint = st.text_input(',
    '                "API 端点",',
    '                value="http://localhost:1234/v1",',
    '                help="OCR API 端点（OpenAI 兼容格式）",',
    '                key="ocr_endpoint"',
    '            )',
    '            ocr_model = st.text_input(',
    '                "模型名称",',
    '                value="chandra",',
    '                help="OCR 模型名称",',
    '                key="ocr_model"',
    '            )',
    '            ocr_api_key = st.text_input(',
    '                "API Key（可选）",',
    '                value="",',
    '                type="password",',
    '                help="如果 API 需要认证",',
    '                key="ocr_api_key"',
    '            )',
    '            ocr_output_format = st.selectbox(',
    '                "输出格式",',
    '                options=["json", "html", "markdown"],',
    '                index=0,',
    '                help="JSON 格式包含坐标信息（推荐）",',
    '                key="ocr_output_format"',
    '            )',
    '',
    '        # 图像预处理',
    '        with st.expander("🖼️ 图像预处理", expanded=False):',
    '            col1, col2 = st.columns(2)',
    '            with col1:',
    '                ocr_resize_max = st.number_input(',
    '                    "最大图像尺寸",',
    '                    min_value=512,',
    '                    max_value=4096,',
    '                    value=2048,',
    '                    step=256,',
    '                    help="图像最大边长（像素）",',
    '                    key="ocr_resize_max"',
    '                )',
    '                ocr_image_format = st.selectbox(',
    '                    "图像格式",',
    '                    options=["PNG", "JPEG"],',
    '                    index=0,',
    '                    help="发送给 API 的图像格式",',
    '                    key="ocr_image_format"',
    '                )',
    '            with col2:',
    '                if ocr_image_format == "JPEG":',
    '                    ocr_image_quality = st.slider(',
    '                        "JPEG 质量",',
    '                        min_value=50,',
    '                        max_value=100,',
    '                        value=95,',
    '                        help="JPEG 压缩质量",',
    '                        key="ocr_image_quality"',
    '                    )',
    '                else:',
    '                    ocr_image_quality = 95',
    '',
    '        # 高级选项（包含并发控制）',
    '        with st.expander("⚙️ 高级选项", expanded=False):',
    '            st.markdown("**⚡ 并发控制**")',
    '            col1, col2 = st.columns(2)',
    '            with col1:',
    '                ocr_concurrency = st.number_input(',
    '                    "最大并发数",',
    '                    min_value=1,',
    '                    max_value=20,',
    '                    value=5,',
    '                    help="同时处理的页面数",',
    '                    key="ocr_concurrency"',
    '                )',
    '                ocr_batch_size = st.number_input(',
    '                    "批次大小",',
    '                    min_value=1,',
    '                    max_value=50,',
    '                    value=10,',
    '                    help="每批处理的页面数",',
    '                    key="ocr_batch_size"',
    '                )',
    '            with col2:',
    '                ocr_batch_rest = st.number_input(',
    '                    "批次休息时间（秒）",',
    '                    min_value=0.0,',
    '                    max_value=10.0,',
    '                    value=2.0,',
    '                    step=0.5,',
    '                    help="批次间的休息时间",',
    '                    key="ocr_batch_rest"',
    '                )',
    '                ocr_max_retries = st.number_input(',
    '                    "最大重试次数",',
    '                    min_value=1,',
    '                    max_value=10,',
    '                    value=3,',
    '                    help="API 调用失败时的重试次数",',
    '                    key="ocr_max_retries"',
    '                )',
    '',
    '            st.markdown("---")',
    '            st.markdown("**⚙️ 其他设置**")',
    '            ocr_timeout = st.number_input(',
    '                "API 超时时间（秒）",',
    '                min_value=30,',
    '                max_value=300,',
    '                value=120,',
    '                help="单个 API 请求的超时时间",',
    '                key="ocr_timeout"',
    '            )',
    '',
]

print(f"\n[INFO] Generated {len(new_config)} lines of new config")

# 替换旧配置
lines = lines[:start_idx] + new_config + lines[end_idx:]

print(f"[OK] Replaced lines {start_idx+1} to {end_idx}")

# 保存文件
streamlit_file.write_text('\n'.join(lines), encoding='utf-8')

print("\n[SUCCESS] File updated!")
print("\nChanges:")
print("1. Moved concurrency control into Advanced Options")
print("2. Removed 'Enable Page Anchors' checkbox (using unified config)")
print("3. Reorganized layout for better UX")
