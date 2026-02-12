"""
测试 Chandra 的结构化输出能力

使用不同的 JSON Schema 测试 Chandra 是否支持强制结构化输出
"""

import json
import base64
import requests
from pathlib import Path
from PIL import Image
from io import BytesIO

# 配置
LM_STUDIO_ENDPOINT = "http://localhost:1234/v1/chat/completions"
TEST_IMAGE_PATH = "path/to/your/test/image.png"  # 替换为你的测试图片路径

# 加载 JSON Schemas
with open("test_chandra_json_schemas.json", "r", encoding="utf-8") as f:
    schemas = json.load(f)["schemas"]

def image_to_base64(image_path):
    """将图片转为 base64"""
    img = Image.open(image_path)
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

def test_schema(schema_name, schema_data, image_base64):
    """测试单个 schema"""
    print(f"\n{'='*80}")
    print(f"测试 Schema: {schema_data['name']}")
    print(f"描述: {schema_data['description']}")
    print(f"{'='*80}\n")

    # 构建请求
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
                        "text": "Extract all text and structure from this image. Output as JSON."
                    }
                ]
            }
        ],
        "max_tokens": 4096,
        "temperature": 0.1,
        # 尝试使用 response_format 强制 JSON 输出
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "schema": schema_data["schema"],
                "strict": True
            }
        }
    }

    try:
        # 发送请求
        response = requests.post(LM_STUDIO_ENDPOINT, json=payload)
        response.raise_for_status()

        result = response.json()
        content = result["choices"][0]["message"]["content"]

        # 尝试解析为 JSON
        try:
            parsed_json = json.loads(content)
            print("✅ 成功返回结构化 JSON")
            print(f"\n输出预览:")
            print(json.dumps(parsed_json, indent=2, ensure_ascii=False)[:500])
            print("...")

            # 保存完整输出
            output_file = f"chandra_output_{schema_name}.json"
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(parsed_json, f, indent=2, ensure_ascii=False)
            print(f"\n完整输出已保存到: {output_file}")

            return True, parsed_json

        except json.JSONDecodeError as e:
            print(f"❌ 返回的不是有效 JSON")
            print(f"错误: {e}")
            print(f"\n原始输出:")
            print(content[:500])
            return False, content

    except requests.exceptions.RequestException as e:
        print(f"❌ API 请求失败")
        print(f"错误: {e}")
        return False, None

def main():
    print("Chandra 结构化输出测试")
    print("="*80)

    # 检查测试图片
    if not Path(TEST_IMAGE_PATH).exists():
        print(f"❌ 测试图片不存在: {TEST_IMAGE_PATH}")
        print("\n请修改脚本中的 TEST_IMAGE_PATH 变量")
        return

    # 转换图片
    print(f"加载测试图片: {TEST_IMAGE_PATH}")
    image_base64 = image_to_base64(TEST_IMAGE_PATH)
    print(f"图片大小: {len(image_base64)} bytes (base64)")

    # 测试每个 schema
    results = {}
    for schema_name, schema_data in schemas.items():
        success, output = test_schema(schema_name, schema_data, image_base64)
        results[schema_name] = {
            "success": success,
            "output": output
        }

    # 总结
    print(f"\n{'='*80}")
    print("测试总结")
    print(f"{'='*80}\n")

    for schema_name, result in results.items():
        status = "✅ 成功" if result["success"] else "❌ 失败"
        print(f"{status} - {schema_name}")

    print(f"\n{'='*80}")

if __name__ == "__main__":
    main()
