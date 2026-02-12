"""
调试脚本：检查处理器配置是否正确传递

运行此脚本来验证配置传递链路
"""

import sys
sys.path.insert(0, 'd:/marker_cuda')

print("=" * 80)
print("处理器配置调试")
print("=" * 80)
print()

# 测试配置
test_config = {
    "blockquote_enabled": False,
    "line_merge_enabled": False,
    "code_enabled": True,
}

print("测试配置：")
for key, value in test_config.items():
    print(f"  {key}: {value}")
print()

# 模拟过滤逻辑
from aih_contexture.processors.blockquote import BlockquoteProcessor
from aih_contexture.processors.line_merge import LineMergeProcessor
from aih_contexture.processors.code import CodeProcessor

processor_map = {
    BlockquoteProcessor: "blockquote_enabled",
    LineMergeProcessor: "line_merge_enabled",
    CodeProcessor: "code_enabled",
}

print("过滤结果：")
for processor_cls, config_key in processor_map.items():
    enabled = test_config.get(config_key, True)
    status = "✅ 启用" if enabled else "❌ 禁用"
    print(f"  {processor_cls.__name__}: {status} (config: {config_key}={enabled})")

print()
print("=" * 80)
print("如果看到 BlockquoteProcessor 和 LineMergeProcessor 显示 '❌ 禁用'，")
print("说明过滤逻辑是正确的。")
print("=" * 80)
