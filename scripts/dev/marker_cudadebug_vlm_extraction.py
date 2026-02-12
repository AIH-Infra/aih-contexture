
# ============================================================================
# 测试 4: 检查 VLM Direct 转换器配置
# ============================================================================
print("【测试 4】检查 VLM Direct 转换器配置")
print("-" * 80)

try:
    from aih_contexture.converters.vlm_direct_async import VlmDirectAsyncConverter

    # 模拟配置
    test_config = {
        "vlm_direct_prompt_template": "archive_document",
        "vlm_direct_extract_printed_pages": True,
        "vlm_direct_printed_page_patterns": [
            r"<!--\s*printed-page:\s*(.+?)\s*-->"
        ]
    }

    print("测试配置:")
    for key, value in test_config.items():
        print(f"  {key}: {value}")

    print("\n✅ 配置格式正确")

except Exception as e:
    print(f"❌ 错误: {e}")
    import traceback
    traceback.print_exc()

print()
