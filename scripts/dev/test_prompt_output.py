"""快速测试：检查档案文献模板的提示词输出"""
import sys
sys.path.insert(0, 'd:/marker_cuda')

from aih_contexture.prompts import PromptBuilder

# 构建档案文献模板
template = PromptBuilder.from_template("archive_document")
prompt = template.build_prompt()

print("=" * 80)
print("档案文献模板提示词检查")
print("=" * 80)
print()

# 检查关键词
keywords = ["printed-page", "档案编号", "SC 001"]
print("关键词检查：")
for kw in keywords:
    found = kw in prompt
    print(f"  {'✅' if found else '❌'} {kw}: {found}")

print()
print("提示词长度:", len(prompt), "字符")
print()

# 查找 printed-page 相关内容
if "printed-page" in prompt:
    idx = prompt.find("printed-page")
    start = max(0, idx - 300)
    end = min(len(prompt), idx + 500)
    print("提示词中 'printed-page' 的上下文：")
    print("-" * 80)
    print(prompt[start:end])
    print("-" * 80)
else:
    print("❌ 提示词中没有 'printed-page'！")

print()
print("完整提示词保存到 prompt_output.txt")
with open("d:/marker_cuda/prompt_output.txt", "w", encoding="utf-8") as f:
    f.write(prompt)
