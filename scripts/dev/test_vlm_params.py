"""
测试 VLM 提示词模板系统的参数传导

用于验证：
1. API 参数是否正确传递
2. 不同配置是否产生不同的输出
3. 模板系统是否正常工作
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aih_contexture.converters.vlm_direct_async import VlmDirectAsyncConverter
from aih_contexture.prompts import PromptBuilder

def test_api_params():
    """测试 API 参数传导"""

    print("=" * 80)
    print("测试 1: 高准确性配置 (temperature=0.0)")
    print("=" * 80)

    config1 = {
        "vlm_direct_base_url": "https://api.openai.com/v1",
        "vlm_direct_model": "gpt-4o",
        "vlm_direct_api_key": "sk-test",
        "vlm_direct_prompt_template": "modern_publication",
        "vlm_direct_api_preset": "high_accuracy",
    }

    converter1 = VlmDirectAsyncConverter(config1)
    print(f"API Type: {converter1.api_type}")
    print(f"API Params: {converter1.api_params}")
    print(f"Prompt length: {len(converter1.prompt)} chars")
    print()

    print("=" * 80)
    print("测试 2: 创意配置 (temperature=0.5)")
    print("=" * 80)

    config2 = {
        "vlm_direct_base_url": "https://api.openai.com/v1",
        "vlm_direct_model": "gpt-4o",
        "vlm_direct_api_key": "sk-test",
        "vlm_direct_prompt_template": "modern_publication",
        "vlm_direct_api_preset": "creative",
    }

    converter2 = VlmDirectAsyncConverter(config2)
    print(f"API Type: {converter2.api_type}")
    print(f"API Params: {converter2.api_params}")
    print(f"Prompt length: {len(converter2.prompt)} chars")
    print()

    print("=" * 80)
    print("测试 3: 自定义 API 参数")
    print("=" * 80)

    config3 = {
        "vlm_direct_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "vlm_direct_model": "qwen-vl-max",
        "vlm_direct_api_key": "sk-test",
        "vlm_direct_prompt_template": "ancient_chinese",
        "vlm_direct_temperature": 0.1,
        "vlm_direct_top_p": 0.2,
        "vlm_direct_top_k": 5,
    }

    converter3 = VlmDirectAsyncConverter(config3)
    print(f"API Type: {converter3.api_type}")
    print(f"API Params: {converter3.api_params}")
    print(f"Prompt length: {len(converter3.prompt)} chars")
    print()

    print("=" * 80)
    print("测试 4: 旧模式（自定义提示词）")
    print("=" * 80)

    config4 = {
        "vlm_direct_base_url": "https://api.openai.com/v1",
        "vlm_direct_model": "gpt-4o",
        "vlm_direct_api_key": "sk-test",
        "vlm_direct_prompt": "Custom prompt here",
    }

    converter4 = VlmDirectAsyncConverter(config4)
    print(f"API Params: {converter4.api_params}")
    print(f"Prompt: {converter4.prompt[:50]}...")
    print()

    print("=" * 80)
    print("测试 5: 空提示词（应该使用模板系统）")
    print("=" * 80)

    config5 = {
        "vlm_direct_base_url": "https://api.openai.com/v1",
        "vlm_direct_model": "gpt-4o",
        "vlm_direct_api_key": "sk-test",
        "vlm_direct_prompt": "",  # 空字符串
        "vlm_direct_prompt_template": "modern_publication",
        "vlm_direct_api_preset": "high_accuracy",
    }

    converter5 = VlmDirectAsyncConverter(config5)
    print(f"API Type: {converter5.api_type}")
    print(f"API Params: {converter5.api_params}")
    print(f"Prompt length: {len(converter5.prompt)} chars")
    print()

    # 验证参数差异
    print("=" * 80)
    print("验证结果")
    print("=" * 80)

    assert converter1.api_params["temperature"] == 0.0, "测试1失败：temperature 应该是 0.0"
    assert converter2.api_params["temperature"] == 0.5, "测试2失败：temperature 应该是 0.5"
    assert converter3.api_params["temperature"] == 0.1, "测试3失败：temperature 应该是 0.1"
    assert converter3.api_params["top_k"] == 5, "测试3失败：top_k 应该是 5"
    assert converter4.api_params == {}, "测试4失败：旧模式应该没有 API 参数"
    assert converter5.api_params["temperature"] == 0.0, "测试5失败：空提示词应该使用模板系统"

    print("✅ 所有测试通过！")
    print()
    print("结论：")
    print("1. API 参数正确传导")
    print("2. 不同配置产生不同的参数")
    print("3. 空提示词正确使用模板系统")
    print("4. 旧模式向后兼容")

def test_prompt_templates():
    """测试提示词模板"""

    print("\n" + "=" * 80)
    print("测试提示词模板内容")
    print("=" * 80)

    # 测试不同模板
    templates = [
        "modern_publication",
        "ancient_chinese",
        "archive_document",
    ]

    for template_name in templates:
        print(f"\n模板: {template_name}")
        print("-" * 80)

        template = PromptBuilder.from_template(template_name)
        prompt = template.build_prompt()

        print(f"Prompt 长度: {len(prompt)} chars")
        print(f"包含脚注指导: {'Footnote' in prompt}")
        print(f"包含元素存在性原则: {'Element Existence' in prompt}")
        print(f"包含输出要求: {'Output Requirements' in prompt}")

        # 显示前200个字符
        print(f"\n前200字符:")
        print(prompt[:200])

if __name__ == "__main__":
    print("VLM 提示词模板系统 - 参数传导测试\n")

    try:
        test_api_params()
        test_prompt_templates()
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
