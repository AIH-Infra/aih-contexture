"""
重新组织 OCR Direct 配置界面
1. 移除独立的并发控制区域
2. 将并发控制整合进高级选项
3. 移除启用页码锚点复选框
"""
from pathlib import Path

streamlit_file = Path("marker/scripts/streamlit_app.py")

print("Step 1: Reading file...")
lines = streamlit_file.read_text(encoding='utf-8').split('\n')

print("\nStep 2: Finding OCR Direct config section...")

# 找到 OCR Direct 配置的开始位置
start_idx = None
for i, line in enumerate(lines):
    if 'elif conversion_mode == "ocr_direct":' in line:
        start_idx = i
        print(f"[OK] Found OCR Direct config at line {i+1}")
        break

if not start_idx:
    print("[ERROR] Could not find OCR Direct config")
    exit(1)

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
]

print("\nStep 3: Creating new config structure...")
print(f"[OK] Generated {len(new_config)} lines for API and Image config")

# 保存到临时文件查看
temp_file = Path("d:/marker_cuda/ocr_config_part1.txt")
temp_file.write_text('\n'.join(new_config), encoding='utf-8')
print(f"[OK] Saved part 1 to {temp_file}")

print("\n[INFO] Next: Create part 2 with Advanced Options")
