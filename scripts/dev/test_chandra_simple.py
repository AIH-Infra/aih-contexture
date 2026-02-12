"""
Chandra 结构化输出测试 - 简化版

不使用 response_format，而是通过 prompt 引导输出 JSON
"""

import json
import base64
import requests
from pathlib import Path
from PIL import Image
from io import BytesIO

# 配置
LM_STUDIO_ENDPOINT = "http://localhost:1234/v1/chat/completions"
TEST_IMAGE_PATH = r"C:\Users\vellichor\Desktop\Rudolf Haym_(Herder Nach Seinem Leben Und Seinen Werken Dargestellt)_R. Gaertners Verlagsbuchhandlung Hermann Heyfelder_1885_001_148.png"

def image_to_base64(image_path):
    """将图片转为 base64"""
    img = Image.open(image_path)
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

def test_prompt_based_json(image_base64, test_name, prompt):
    """通过 prompt 引导输出 JSON"""
    print(f"\n{'='*80}")
    print(f"测试: {test_name}")
    print(f"{'='*80}\n")
    print(f"Prompt: {prompt[:100]}...")

    payload = {
        "model": "chandra",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_base64}"
                        }
                    },
                    {
                        "type": "text",
                        "text": prompt
                    }
                ]
            }
        ],
        "max_tokens": 4096,
        "temperature": 0.1
    }

    try:
        response = requests.post(LM_STUDIO_ENDPOINT, json=payload)
        response.raise_for_status()

        result = response.json()
        content = result["choices"][0]["message"]["content"]

        # 尝试解析为 JSON
        try:
            parsed_json = json.loads(content)
            print("✅ 成功返回 JSON")
            print(f"\n输出预览:")
            print(json.dumps(parsed_json, indent=2, ensure_ascii=False)[:500])

            # 保存
            output_file = f"chandra_output_{test_name}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(parsed_json, f, indent=2, ensure_ascii=False)
            print(f"\n✅ 完整输出已保存: {output_file}")

            return True, parsed_json

        except json.JSONDecodeError:
            print(f"❌ 返回的不是有效 JSON")
            print(f"\n原始输出:")
            print(content[:500])

            # 保存原始输出
            output_file = f"chandra_output_{test_name}.txt"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"\n原始输出已保存: {output_file}")

            return False, content

    except Exception as e:
        print(f"❌ 请求失败: {e}")
        return False, None

def main():
    print("Chandra 结构化输出测试 - 简化版")
    print("="*80)

    # 检查图片
    if not Path(TEST_IMAGE_PATH).exists():
        print(f"❌ 测试图片不存在: {TEST_IMAGE_PATH}")
        print("\n请修改 TEST_IMAGE_PATH 变量")
        return

    print(f"加载图片: {TEST_IMAGE_PATH}")
    image_base64 = image_to_base64(TEST_IMAGE_PATH)

    # 测试用例
    tests = {
        "test1_basic": {
            "name": "基础 JSON 输出",
            "prompt": """Extract all text from this image and output as JSON with this structure:
{
  "blocks": [
    {
      "text": "extracted text",
      "bbox": [x1, y1, x2, y2],
      "type": "text"
    }
  ]
}"""
        },
        "test2_detailed": {
            "name": "详细 JSON 输出",
            "prompt": """Extract all text and structure from this image. Output as JSON with:
- page dimensions
- blocks with id, type, text, bbox, confidence
- formatting info (bold, italic)

Example:
{
  "page": {"width": 800, "height": 1000},
  "blocks": [
    {
      "id": "block_1",
      "type": "text",
      "text": "...",
      "bbox": [x1, y1, x2, y2],
      "confidence": 0.95,
      "formatting": {"bold": false, "italic": false}
    }
  ]
}"""
        },
        "test3_simple": {
            "name": "最简 JSON",
            "prompt": "Extract text as JSON: {\"text\": \"all text here\"}"
        }
    }

    # 运行测试
    results = {}
    for test_id, test_data in tests.items():
        success, output = test_prompt_based_json(
            image_base64,
            test_id,
            test_data["prompt"]
        )
        results[test_id] = success

    # 总结
    print(f"\n{'='*80}")
    print("测试总结")
    print(f"{'='*80}\n")

    for test_id, success in results.items():
        status = "✅" if success else "❌"
        print(f"{status} {tests[test_id]['name']}")

if __name__ == "__main__":
    main()
