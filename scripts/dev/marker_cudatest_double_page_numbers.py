"""
测试双层页码系统
"""

# 测试 CustomIDInjector
from aih_contexture.formatters import CustomIDInjector

print("=" * 60)
print("测试 CustomIDInjector")
print("=" * 60)

# 测试 1: 自动生成
print("\n1. 测试自动生成")
injector = CustomIDInjector("auto", {
    'prefix': 'sc',
    'start': 1,
    'padding': 3,
    'count': 5
})
for i in range(5):
    custom_id = injector.get_custom_id(i)
    print(f"  页面 {i}: {custom_id}")

# 测试 2: 手动输入列表
print("\n2. 测试手动输入列表")
injector = CustomIDInjector("list", "档-001, 档-002, 档-003")
for i in range(3):
    custom_id = injector.get_custom_id(i)
    print(f"  页面 {i}: {custom_id}")

# 测试 3: JSON 文件
print("\n3. 测试 JSON 文件")
import json
json_data = json.dumps({"0": "A001", "1": "A002", "2": "A003"})
injector = CustomIDInjector("file", json_data)
for i in range(3):
    custom_id = injector.get_custom_id(i)
    print(f"  页面 {i}: {custom_id}")

# 测试 4: CSV 文件
print("\n4. 测试 CSV 文件")
csv_data = "page_index,custom_id\n0,B001\n1,B002\n2,B003"
injector = CustomIDInjector("file", csv_data)
for i in range(3):
    custom_id = injector.get_custom_id(i)
    print(f"  页面 {i}: {custom_id}")

print("\n" + "=" * 60)
print("所有测试完成！")
print("=" * 60)
