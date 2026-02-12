"""
测试 Markdown 噪音清理处理器

验证处理器是否正确清理 OCR 识别出的 Markdown 符号噪音
"""

import sys
sys.path.insert(0, 'd:/marker_cuda')

print("=" * 80)
print("测试 Markdown 噪音清理处理器")
print("=" * 80)
print()

# 测试配置
test_config = {
    "markdown_noise_removal_enabled": True,
    "markdown_noise_cleaning_level": "medium",  # 清理 #, >, -, *, +
    "markdown_noise_line_start_only": True,
    "markdown_noise_custom_symbols": "",
}

print("测试配置：")
for key, value in test_config.items():
    print(f"  {key}: {value}")
print()

# 导入处理器
from aih_contexture.processors.markdown_noise import MarkdownNoiseRemovalProcessor

# 创建处理器实例
processor = MarkdownNoiseRemovalProcessor(config=test_config)

print("处理器配置：")
print(f"  清理级别: {processor.markdown_noise_cleaning_level}")
print(f"  只清理行首: {processor.markdown_noise_line_start_only}")
print(f"  自定义符号: '{processor.markdown_noise_custom_symbols}'")
print()

# 测试文本清理
test_cases = [
    "# 1 这是一个标题",
    "> 这是一个引用",
    "- 这是一个列表项",
    "* 这是另一个列表项",
    "+ 这是第三个列表项",
    "正常文本 # 中间的符号",
    "正常文本",
]

print("测试文本清理：")
print("-" * 80)
for text in test_cases:
    cleaned = processor.clean_text(text)
    if cleaned != text:
        print(f"✅ 清理成功:")
        print(f"   原文: {text}")
        print(f"   清理后: {cleaned}")
    else:
        print(f"⚪ 无需清理: {text}")
print("-" * 80)
print()

print("=" * 80)
print("测试完成！")
print("=" * 80)
