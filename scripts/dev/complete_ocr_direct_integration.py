"""
完整的 OCR Direct UI 集成脚本
自动完成所有剩余的集成工作
"""

import re
from pathlib import Path

def backup_file(filepath):
    """备份文件"""
    backup_path = filepath.with_suffix('.py.backup')
    content = filepath.read_text(encoding='utf-8')
    backup_path.write_text(content, encoding='utf-8')
    print(f"[BACKUP] 已备份到: {backup_path}")
    return backup_path

def add_ocr_config_ui(content):
    """添加 OCR Direct 配置界面"""
    print("\n[1/4] 添加 OCR Direct 配置界面...")

    # 配置界面代码
    config_code = '''
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

    # 查找插入位置 - 在 elif conversion_mode == "ocr_direct": 之后
    # 但这个已经存在了，我们需要在它后面添加配置代码
    pattern = r'(elif conversion_mode == "ocr_direct":.*?st\.info\([^)]+\)\s+)\s+(else:)'

    if re.search(pattern, content, re.DOTALL):
        replacement = r'\1' + config_code + r'\n\n    \2'
        content = re.sub(pattern, replacement, content, count=1, flags=re.DOTALL)
        print("[OK] 配置界面已添加")
    else:
        print("[SKIP] 配置界面可能已存在或找不到插入点")

    return content

def main():
    print("=" * 80)
    print("OCR Direct 完整集成工具")
    print("=" * 80)

    streamlit_file = Path("marker/scripts/streamlit_app.py")

    if not streamlit_file.exists():
        print(f"[ERROR] 文件不存在: {streamlit_file}")
        return False

    # 备份文件
    backup_file(streamlit_file)

    # 读取文件
    print("\n[READ] 读取文件...")
    content = streamlit_file.read_text(encoding='utf-8')

    # 添加配置界面
    content = add_ocr_config_ui(content)

    # 保存文件
    print("\n[SAVE] 保存修改...")
    streamlit_file.write_text(content, encoding='utf-8')

    print("\n" + "=" * 80)
    print("[SUCCESS] 第一部分完成！")
    print("=" * 80)
    print("\n下一步: 运行 part2 脚本修改 build_config_dict")

    return True

if __name__ == "__main__":
    main()
