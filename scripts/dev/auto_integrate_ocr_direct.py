"""
自动集成 OCR Direct 到 Streamlit UI

此脚本会自动修改 streamlit_app.py 文件，添加 OCR Direct 支持
"""

import re
from pathlib import Path

def integrate_ocr_direct():
    """自动集成 OCR Direct"""

    streamlit_file = Path("marker/scripts/streamlit_app.py")

    if not streamlit_file.exists():
        print(f"❌ 文件不存在: {streamlit_file}")
        return False

    print("[1/3] 读取 streamlit_app.py...")
    content = streamlit_file.read_text(encoding='utf-8')

    # 修改 1: 添加 ocr_direct 选项
    print("\n[2/3] 修改 1: 添加转换模式选项...")
    content = content.replace(
        'options=["traditional", "vlm_direct"],',
        'options=["traditional", "vlm_direct", "ocr_direct"],'
    )

    # 修改 2: 添加 format_func
    content = content.replace(
        '"vlm_direct": "🚀 VLM Direct 模式（纯 VLM 异步并发）",\n        }.get(x, x),',
        '"vlm_direct": "🚀 VLM Direct 模式（纯 VLM 异步并发）",\n            "ocr_direct": "📚 OCR Direct 模式（专业 OCR）",\n        }.get(x, x),'
    )

    print("[OK] 修改 1 完成")

    # 修改 3: 添加模式说明
    print("\n[3/3] 修改 2: 添加模式说明...")

    ocr_direct_info = '''    elif conversion_mode == "ocr_direct":
        st.info(
            "📚 **OCR Direct 模式**\\n\\n"
            "- ✅ 使用专业 OCR 引擎（Chandra）\\n"
            "- ✅ 异步并发处理\\n"
            "- ✅ 支持手写、表格、公式\\n"
            "- ✅ 保留坐标信息\\n"
            "- ✅ 批处理与休息间隔\\n\\n"
            "**适用场景**：手写文档、复杂表格、数学公式、古籍文献"
        )
'''

    # 在 vlm_direct 的 st.info 后面插入
    pattern = r'(\s+if conversion_mode == "vlm_direct":\s+st\.info\([^)]+\))\s+(else:)'
    replacement = r'\1\n' + ocr_direct_info + r'\n    \2'
    content = re.sub(pattern, replacement, content, count=1)

    print("[OK] 修改 2 完成")

    # 保存文件
    print("\n[SAVE] 保存修改...")
    streamlit_file.write_text(content, encoding='utf-8')

    print("\n[SUCCESS] 集成完成！")
    print("\n下一步:")
    print("1. 需要手动添加 OCR Direct 配置界面（Line 1142）")
    print("2. 需要修改 build_config_dict 函数")
    print("3. 查看 OCR_DIRECT_UI_PATCH_PART1.md 和 PART2.md 获取详细代码")

    return True

if __name__ == "__main__":
    print("=" * 80)
    print("OCR Direct UI 自动集成工具")
    print("=" * 80)

    success = integrate_ocr_direct()

    if success:
        print("\n" + "=" * 80)
        print("[SUCCESS] 部分集成完成！转换模式选择已添加。")
        print("=" * 80)
    else:
        print("\n[FAILED] 集成失败")
