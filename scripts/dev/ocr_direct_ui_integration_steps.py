"""
OCR Direct UI 集成脚本

由于 streamlit_app.py 文件较大，直接修改容易出错。
此脚本提供手动集成的具体步骤。
"""

print("=" * 80)
print("OCR Direct UI 集成步骤")
print("=" * 80)

print("\n步骤 1: 修改转换模式选择（Line 460-470）")
print("-" * 80)
print("找到这段代码：")
print('''
    conversion_mode = st.radio(
        "选择转换模式",
        options=["traditional", "vlm_direct"],
''')
print("\n修改为：")
print('''
    conversion_mode = st.radio(
        "选择转换模式",
        options=["traditional", "vlm_direct", "ocr_direct"],
''')
print("\n并在 format_func 中添加：")
print('''
            "ocr_direct": "📚 OCR Direct 模式（专业 OCR）",
''')

print("\n\n步骤 2: 修改模式说明（Line 472-489）")
print("-" * 80)
print("在 if conversion_mode == 'vlm_direct': 后面添加：")
print('''
    elif conversion_mode == "ocr_direct":
        st.info(
            "📚 **OCR Direct 模式**\\n\\n"
            "- ✅ 使用专业 OCR 引擎（Chandra）\\n"
            "- ✅ 异步并发处理\\n"
            "- ✅ 支持手写、表格、公式\\n"
            "- ✅ 保留坐标信息\\n"
            "- ✅ 批处理与休息间隔\\n\\n"
            "**适用场景**：手写文档、复杂表格、数学公式、古籍文献"
        )
''')

print("\n\n步骤 3: 添加 OCR Direct 配置界面（Line 1142）")
print("-" * 80)
print("找到 Line 1142 的 'else:' (在 VLM Direct 配置后)")
print("将其改为 'elif conversion_mode == \"ocr_direct\":'")
print("然后复制以下完整配置代码...")

print("\n\n由于配置代码较长，已保存到单独的文件中。")
print("请查看: OCR_DIRECT_UI_CONFIG_CODE.py")

print("\n" + "=" * 80)
print("集成完成后，重启 Streamlit 应用即可看到 OCR Direct 选项")
print("=" * 80)
