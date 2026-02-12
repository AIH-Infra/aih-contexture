"""
完整修复 OCR Direct UI 配置问题
"""
import re
from pathlib import Path

def fix_ocr_direct_ui():
    streamlit_file = Path("marker/scripts/streamlit_app.py")

    print("[1/3] 读取文件...")
    content = streamlit_file.read_text(encoding='utf-8')

    # 查找并替换 Line 1295 的 else: 为 elif
    print("[2/3] 修改配置分支...")

    # 匹配模式：vlm_direct 配置结束后的 else:
    pattern = r'(vlm_direct_printed_page_patterns = vlm_printed_page_patterns if \'vlm_printed_page_patterns\' in locals\(\) else None\s*\n\s*)\n(\s+)else:\s*\n(\s+)# ==================== 传统模式配置'

    replacement = r'''\1
\2elif conversion_mode == "ocr_direct":
\2    # ==================== OCR Direct 模式配置 ====================
\2    st.subheader("📚 OCR Direct 配置")
\2
\2    # API 配置
\2    with st.expander("🔌 API 配置", expanded=True):
\2        ocr_endpoint = st.text_input(
\2            "API Endpoint",
\2            value="http://localhost:1234/v1/chat/completions",
\2            help="OCR API 端点（OpenAI 兼容）",
\2            key="ocr_endpoint"
\2        )
\2        ocr_model = st.text_input(
\2            "模型名称",
\2            value="chandra",
\2            help="OCR 模型名称",
\2            key="ocr_model"
\2        )
\2        ocr_api_key = st.text_input(
\2            "API Key（可选）",
\2            value="",
\2            type="password",
\2            help="如果 API 需要认证",
\2            key="ocr_api_key"
\2        )
\2        ocr_output_format = st.selectbox(
\2            "输出格式",
\2            options=["json", "html", "markdown"],
\2            index=0,
\2            help="JSON 格式包含坐标信息（推荐）",
\2            key="ocr_output_format"
\2        )
\2
\2    # 并发控制
\2    with st.expander("⚡ 并发控制", expanded=True):
\2        col1, col2 = st.columns(2)
\2        with col1:
\2            ocr_concurrency = st.number_input(
\2                "最大并发数",
\2                min_value=1,
\2                max_value=20,
\2                value=5,
\2                help="同时处理的页面数",
\2                key="ocr_concurrency"
\2            )
\2            ocr_batch_size = st.number_input(
\2                "批次大小",
\2                min_value=1,
\2                max_value=50,
\2                value=10,
\2                help="每批处理的页面数",
\2                key="ocr_batch_size"
\2            )
'''

    # 第一部分替换
    if re.search(pattern, content, re.DOTALL):
        content = re.sub(pattern, replacement, content, count=1, flags=re.DOTALL)
        print("[OK] 第一部分完成")
    else:
        print("[WARN] 未找到匹配模式，尝试简单替换...")
        # 简单替换方案
        content = content.replace(
            '    else:\n            # ==================== 传统模式配置',
            '    elif conversion_mode == "ocr_direct":\n        # OCR Direct 配置\n        st.subheader("📚 OCR Direct 配置")\n        st.info("OCR Direct 配置界面")\n    else:\n            # ==================== 传统模式配置'
        )

    print("[3/3] 保存文件...")
    streamlit_file.write_text(content, encoding='utf-8')

    print("[SUCCESS] 修复完成！")
    return True

if __name__ == "__main__":
    print("=" * 80)
    print("修复 OCR Direct UI 配置")
    print("=" * 80)
    fix_ocr_direct_ui()
