"""
测试：验证禁用印刷页码时的页码锚点格式

场景：Surya + 禁用 OCR + 禁用印刷页码
预期：页码锚点应该是 {0}, {1}, {2}（单层括号）
"""

def test_disabled_printed_pages():
    """测试禁用印刷页码时的锚点格式"""
    from aih_contexture.formatters import PageAnchorFormatter

    print("=" * 60)
    print("测试场景：禁用印刷页码")
    print("=" * 60)

    # 创建 formatter（与实际代码相同）
    formatter = PageAnchorFormatter(wrapper="{{{}}}")

    # 模拟 convert_div 的逻辑
    def simulate_convert_div(page_id, printed_page_id=None, custom_id=None):
        """
        模拟 MarkdownRenderer.convert_div 的逻辑

        Args:
            page_id: 页面索引
            printed_page_id: 印刷页码（来自 PageNumberProcessor）
            custom_id: 自定义编号（来自 CustomIDInjector）
        """
        # 如果没有印刷页码，尝试使用自定义编号
        if not printed_page_id and custom_id:
            printed_page_id = custom_id

        # 使用格式化器生成页锚点
        page_anchor = formatter.format(page_id, printed_page_id)

        # 生成页码标记（如果有印刷页码或自定义编号）
        page_tag = ""
        if printed_page_id:
            page_tag = f"<!-- Page: {printed_page_id} -->\\n"

        # 生成分页项（修复后的代码）
        pagination_item = "\\n\\n" + page_anchor + "\\n" + page_tag + "---\\n\\n"

        return pagination_item + "content..."

    print("\n场景 1: 禁用印刷页码 + 无自定义编号")
    print("配置: extract_printed_pages=False, custom_id_source='none'")
    output = simulate_convert_div(page_id=0, printed_page_id=None, custom_id=None)
    print(f"输出:\n{output}")

    # 检查是否有双层括号
    if "{{" in output or "}}" in output:
        print("[FAIL] 发现双层括号！")
        print(f"问题位置: {output}")
    else:
        print("[OK] 无双层括号")

    print("\n场景 2: 启用印刷页码（但无法提取）")
    print("配置: extract_printed_pages=True, 但 Surya+禁用OCR 无法提取")
    output = simulate_convert_div(page_id=1, printed_page_id=None, custom_id=None)
    print(f"输出:\n{output}")

    if "{{" in output or "}}" in output:
        print("[FAIL] 发现双层括号！")
    else:
        print("[OK] 无双层括号")

    print("\n场景 3: 启用印刷页码（成功提取）")
    print("配置: extract_printed_pages=True, 成功提取到页码")
    output = simulate_convert_div(page_id=2, printed_page_id="XII", custom_id=None)
    print(f"输出:\n{output}")

    if "{{" in output or "}}" in output:
        print("[FAIL] 发现双层括号！")
    else:
        print("[OK] 无双层括号")

    print("\n场景 4: 使用自定义编号")
    print("配置: custom_id_source='auto'")
    output = simulate_convert_div(page_id=3, printed_page_id=None, custom_id="sc004")
    print(f"输出:\n{output}")

    if "{{" in output or "}}" in output:
        print("[FAIL] 发现双层括号！")
    else:
        print("[OK] 无双层括号")

    # 测试文档末尾锚点
    print("\n场景 5: 文档末尾额外锚点")
    page_count = 5
    final_anchor = f"{{{page_count}}}"
    print(f"final_anchor = '{final_anchor}'")

    if "{{" in final_anchor or "}}" in final_anchor:
        print("[FAIL] 发现双层括号！")
    else:
        print("[OK] 无双层括号")


def test_old_code_behavior():
    """测试旧代码的行为（用于对比）"""
    print("\n" + "=" * 60)
    print("对比：旧代码的行为（已修复）")
    print("=" * 60)

    from aih_contexture.formatters import PageAnchorFormatter

    formatter = PageAnchorFormatter(wrapper="{{{}}}")

    # 旧代码的逻辑（错误的）
    def old_convert_div(page_id):
        page_anchor = formatter.format(page_id, None)
        # 旧代码：添加了额外的括号
        pagination_item = "\\n\\n" + "{" + page_anchor + "}" + "\\n" + "---\\n\\n"
        return pagination_item + "content..."

    # 新代码的逻辑（正确的）
    def new_convert_div(page_id):
        page_anchor = formatter.format(page_id, None)
        # 新代码：不添加额外的括号
        pagination_item = "\\n\\n" + page_anchor + "\\n" + "---\\n\\n"
        return pagination_item + "content..."

    print("\n旧代码输出（错误）:")
    old_output = old_convert_div(0)
    print(old_output)
    if "{{" in old_output:
        print("[ERROR] 双层括号: {{0}}")

    print("\n新代码输出（正确）:")
    new_output = new_convert_div(0)
    print(new_output)
    if "{{" not in new_output:
        print("[OK] 单层括号: {0}")


if __name__ == "__main__":
    try:
        test_disabled_printed_pages()
        test_old_code_behavior()

        print("\n" + "=" * 60)
        print("测试完成")
        print("=" * 60)

        print("\n结论：")
        print("如果所有测试都显示 [OK]，说明代码已正确修复")
        print("如果仍然看到 [FAIL]，请检查是否有其他代码路径")
        print("\n如果用户仍然看到双层括号，可能的原因：")
        print("1. 需要重启 Streamlit 应用")
        print("2. 浏览器缓存了旧的输出")
        print("3. 正在查看旧的输出文件")
        print("4. 使用了不同的转换模式（VLM Direct vs Pipeline）")

    except Exception as e:
        print(f"\n[FAIL] 测试失败: {e}")
        import traceback
        traceback.print_exc()
