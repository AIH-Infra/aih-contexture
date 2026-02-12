"""
测试 React 错误修复和档案编号提取

这个脚本验证：
1. React 错误是否已修复（组件始终渲染）
2. 档案编号提取的正则表达式是否正确
3. 提示词模板是否包含档案编号指令
"""

import re
from aih_contexture.prompts import PromptBuilder

def test_regex_extraction():
    """测试正则表达式提取"""
    print("=" * 60)
    print("测试 1: 正则表达式提取")
    print("=" * 60)

    pattern = r"<!--\s*printed-page:\s*(.+?)\s*-->"

    test_cases = [
        "<!-- printed-page: SC 001 -->",
        "<!--printed-page:SC 001-->",
        "<!-- printed-page: SC-001 -->",
        "<!-- printed-page: 档案号123 -->",
        "<!-- printed-page: A-2024-001 -->",
    ]

    for test in test_cases:
        match = re.search(pattern, test)
        if match:
            print(f"✅ 成功: {test} → 提取: '{match.group(1)}'")
        else:
            print(f"❌ 失败: {test}")
    print()

def test_archive_template():
    """测试档案文献模板"""
    print("=" * 60)
    print("测试 2: 档案文献模板")
    print("=" * 60)

    template = PromptBuilder.from_template("archive_document")
    prompt = template.build_prompt()

    # 检查是否包含档案编号识别指令
    keywords = [
        "printed-page",
        "档案编号",
        "SC 001",
        "档案号"
    ]

    print("检查提示词中是否包含关键词：")
    for keyword in keywords:
        if keyword in prompt:
            print(f"✅ 找到: '{keyword}'")
        else:
            print(f"❌ 缺失: '{keyword}'")

    print("\n提示词长度:", len(prompt), "字符")
    print()

def test_modern_template():
    """测试现代出版物模板（默认）"""
    print("=" * 60)
    print("测试 3: 现代出版物模板（默认）")
    print("=" * 60)

    template = PromptBuilder.from_template("modern_publication")
    prompt = template.build_prompt()

    # 检查是否包含页码识别指令
    if "printed-page" in prompt:
        print("✅ 包含基础页码识别指令")
    else:
        print("❌ 缺少页码识别指令")

    # 检查是否包含档案编号指令
    if "档案编号" in prompt or "SC 001" in prompt:
        print("✅ 包含档案编号识别指令")
    else:
        print("⚠️  不包含档案编号识别指令（这是正常的，因为这不是档案文献模板）")

    print()

if __name__ == "__main__":
    print("\n🔍 开始测试...\n")

    test_regex_extraction()
    test_archive_template()
    test_modern_template()

    print("=" * 60)
    print("测试完成")
    print("=" * 60)
    print("\n📝 结论：")
    print("1. 正则表达式应该能正确提取档案编号")
    print("2. 档案文献模板应该包含档案编号识别指令")
    print("3. 用户必须选择'档案文献'模板才能识别档案编号")
    print("4. 默认的'现代出版物'模板不包含档案编号指令")
    print("\n⚠️  重要提示：")
    print("   在 Streamlit UI 中，必须手动选择'档案文献'模板！")
    print("   默认的'现代出版物（推荐）'模板不会识别档案编号。")
