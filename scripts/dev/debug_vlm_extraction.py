"""
VLM 档案编号提取 - 深度调试脚本

这个脚本会：
1. 检查提示词模板是否正确
2. 模拟 VLM 输出并测试正则提取
3. 检查配置传递链路
4. 提供详细的调试信息
"""

import re
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 80)
print("VLM 档案编号提取 - 深度调试")
print("=" * 80)
print()

# ============================================================================
# 测试 1: 检查档案文献模板
# ============================================================================
print("【测试 1】检查档案文献模板")
print("-" * 80)

try:
    from aih_contexture.prompts.templates import ARCHIVE_DOCUMENT

    custom_instructions = ARCHIVE_DOCUMENT.get("custom_instructions", "")

    # 检查关键词
    keywords = {
        "档案编号识别": "档案编号识别" in custom_instructions,
        "printed-page": "printed-page" in custom_instructions,
        "SC 001": "SC 001" in custom_instructions,
        "档案号": "档案号" in custom_instructions,
    }

    print("模板关键词检查：")
    for keyword, found in keywords.items():
        status = "✅" if found else "❌"
        print(f"  {status} {keyword}: {found}")

    if all(keywords.values()):
        print("\n✅ 档案文献模板包含所有必要的指令")
    else:
        print("\n❌ 档案文献模板缺少某些指令")
        print("\n模板内容预览：")
        print(custom_instructions[:500])

except Exception as e:
    print(f"❌ 错误: {e}")

print()

# ============================================================================
# 测试 2: 检查基础提示词中的页码识别
# ============================================================================
print("【测试 2】检查基础提示词中的页码识别")
print("-" * 80)

try:
    from aih_contexture.prompts import PromptBuilder

    template = PromptBuilder.from_template("archive_document")
    full_prompt = template.build_prompt()

    # 检查完整提示词
    checks = {
        "包含 printed-page 标签": "printed-page" in full_prompt,
        "包含页码识别指令": "Printed Page Number Recognition" in full_prompt or "页码识别" in full_prompt,
        "包含档案编号指令": "档案编号" in full_prompt,
    }

    print("完整提示词检查：")
    for check, result in checks.items():
        status = "✅" if result else "❌"
        print(f"  {status} {check}: {result}")

    print(f"\n提示词总长度: {len(full_prompt)} 字符")

    # 搜索关键部分
    if "printed-page" in full_prompt:
        # 找到 printed-page 相关的上下文
        idx = full_prompt.find("printed-page")
        context_start = max(0, idx - 200)
        context_end = min(len(full_prompt), idx + 300)
        print(f"\n提示词中 'printed-page' 的上下文：")
        print("-" * 40)
        print(full_prompt[context_start:context_end])
        print("-" * 40)

except Exception as e:
    print(f"❌ 错误: {e}")
    import traceback
    traceback.print_exc()

print()

# ============================================================================
# 测试 3: 测试正则表达式提取
# ============================================================================
print("【测试 3】测试正则表达式提取")
print("-" * 80)

pattern = r"<!--\s*printed-page:\s*(.+?)\s*-->"

test_cases = [
    ("<!-- printed-page: SC 001 -->", "SC 001"),
    ("<!--printed-page:SC 001-->", "SC 001"),
    ("<!-- printed-page: SC-001 -->", "SC-001"),
    ("<!-- printed-page: 档案号123 -->", "档案号123"),
    ("<!-- printed-page: A-2024-001 -->", "A-2024-001"),
    ("<!-- printed-page:   SC 001   -->", "SC 001"),  # 多余空格
]

print(f"正则表达式: {pattern}\n")

all_passed = True
for test_input, expected in test_cases:
    match = re.search(pattern, test_input)
    if match:
        extracted = match.group(1)
        if extracted == expected:
            print(f"✅ 成功: {test_input}")
            print(f"   提取: '{extracted}'")
        else:
            print(f"⚠️  警告: {test_input}")
            print(f"   期望: '{expected}'")
            print(f"   实际: '{extracted}'")
            all_passed = False
    else:
        print(f"❌ 失败: {test_input}")
        print(f"   无法匹配")
        all_passed = False

if all_passed:
    print("\n✅ 所有正则表达式测试通过")
else:
    print("\n⚠️  部分测试未通过")

print()
