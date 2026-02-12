"""
Chandra 结构化输出测试 - 简化版 (修复编码问题)

不使用 response_format，而是通过 prompt 引导输出 JSON
"""

import json
import base64
import requests
from pathlib import Path
from PIL import Image
from io import BytesIO
import sys

# 设置输出编码
if sys.platform == 'win32':
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')

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
        print("发送请求到 Chandra...")
        response = requests.post(LM_STUDIO_ENDPOINT, json=payload, timeout=120)
        response.raise_for_status()

        result = response.json()
        content = result["choices"][0]["message"]["content"]

        # 尝试解析为 JSON
        try:
            parsed_json = json.loads(content)
            print("[成功] 返回了有效的 JSON")
            print(f"\n输出预览:")
            print(json.dumps(parsed_json, indent=2, ensure_ascii=False)[:500])
            print("...")

            # 保存
            output_file = f"chandra_output_{test_name}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(parsed_json, f, indent=2, ensure_ascii=False)
            print(f"\n[成功] 完整输出已保存: {output_file}")

            return True, parsed_json

        except json.JSONDecodeError as e:
            print(f"[失败] 返回的不是有效 JSON")
            print(f"JSON 解析错误: {e}")
            print(f"\n原始输出 (前500字符):")
            print(content[:500])

            # 保存原始输出
            output_file = f"chandra_output_{test_name}.txt"
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"\n原始输出已保存: {output_file}")

            return False, content

    except requests.exceptions.Timeout:
        print(f"[错误] 请求超时 (120秒)")
        return False, None
    except requests.exceptions.RequestException as e:
        print(f"[错误] API 请求失败: {e}")
        return False, None
    except Exception as e:
        print(f"[错误] 未知错误: {e}")
        return False, None

def main():
    print("Chandra 结构化输出测试 - 简化版")
    print("="*80)

    # 检查图片
    if not Path(TEST_IMAGE_PATH).exists():
        print(f"[错误] 测试图片不存在: {TEST_IMAGE_PATH}")
        print("\n请修改 TEST_IMAGE_PATH 变量")
        return

    print(f"加载图片: {TEST_IMAGE_PATH}")
    try:
        image_base64 = image_to_base64(TEST_IMAGE_PATH)
        print(f"图片大小: {len(image_base64)} bytes (base64)")
    except Exception as e:
        print(f"[错误] 无法加载图片: {e}")
        return

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
        "test2_simple": {
            "name": "最简 JSON",
            "prompt": "Extract all text as JSON: {\"text\": \"all text here\"}"
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
        status = "[成功]" if success else "[失败]"
        print(f"{status} {tests[test_id]['name']}")

    print(f"\n{'='*80}")
    print("测试完成！请查看生成的输出文件。")

if __name__ == "__main__":
    main()
