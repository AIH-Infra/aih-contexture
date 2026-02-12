"""
OCR Direct 功能测试脚本

测试 OcrChandraService + OcrParser + OcrDirectAsyncConverter
"""

import asyncio
from pathlib import Path
from PIL import Image

# 测试配置
TEST_IMAGE_PATH = r"C:\Users\vellichor\Desktop\Rudolf Haym_(Herder Nach Seinem Leben Und Seinen Werken Dargestellt)_R. Gaertners Verlagsbuchhandlung Hermann Heyfelder_1885_001_148.png"
OCR_ENDPOINT = "http://localhost:1234/v1/chat/completions"


def test_ocr_service():
    """测试 OcrChandraService"""
    print("\n" + "="*80)
    print("测试 1: OcrChandraService")
    print("="*80)

    from aih_contexture.services.ocr_chandra import OcrChandraService

    # 创建服务
    service = OcrChandraService(
        ocr_endpoint=OCR_ENDPOINT,
        ocr_model="chandra",
        ocr_output_format="json",
        ocr_max_tokens=4096,
        ocr_temperature=0.1
    )

    # 加载测试图片
    if not Path(TEST_IMAGE_PATH).exists():
        print(f"❌ 测试图片不存在: {TEST_IMAGE_PATH}")
        return False

    img = Image.open(TEST_IMAGE_PATH)
    print(f"✅ 加载图片: {img.size}")

    # 调用 OCR
    try:
        print("📡 调用 OCR API...")
        result = service.process_page(img)

        if isinstance(result, dict):
            blocks = result.get("blocks", [])
            print(f"✅ OCR 成功，识别到 {len(blocks)} 个块")

            # 显示前 3 个块
            for i, block in enumerate(blocks[:3]):
                text = block.get("text", "")[:50]
                bbox = block.get("bbox", [])
                block_type = block.get("type", "unknown")
                print(f"  Block {i+1}: [{block_type}] {text}... @ {bbox}")

            return True
        else:
            print(f"❌ 返回格式错误: {type(result)}")
            return False

    except Exception as e:
        print(f"❌ OCR 调用失败: {e}")
        return False


def test_ocr_parser():
    """测试 OcrParser"""
    print("\n" + "="*80)
    print("测试 2: OcrParser")
    print("="*80)

    from aih_contexture.builders.ocr_parser import OcrParser

    # 创建解析器
    parser = OcrParser()

    # 模拟 OCR 输出
    mock_ocr_output = {
        "blocks": [
            {
                "text": "Test Title",
                "bbox": [100, 50, 500, 80],
                "type": "title"
            },
            {
                "text": "This is a test paragraph with some content.",
                "bbox": [100, 100, 500, 150],
                "type": "text"
            }
        ]
    }

    # 解析为 PageGroup
    try:
        page = parser.parse_to_page(
            mock_ocr_output,
            page_id=0,
            page_size=(600, 800),
            output_format="json"
        )

        print(f"✅ 解析成功")
        print(f"  Page ID: {page.page_id}")
        print(f"  Blocks: {len(page.structure)}")

        for i, block in enumerate(page.structure):
            print(f"  Block {i+1}: {block.block_type}")

        return True

    except Exception as e:
        print(f"❌ 解析失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_ocr_converter():
    """测试 OcrDirectAsyncConverter"""
    print("\n" + "="*80)
    print("测试 3: OcrDirectAsyncConverter")
    print("="*80)

    from aih_contexture.converters.ocr_direct_async import OcrDirectAsyncConverter
    from pydantic import BaseModel

    # 创建配置对象
    class TestConfig(BaseModel):
        ocr_endpoint: str = OCR_ENDPOINT
        ocr_model: str = "chandra"
        ocr_api_key: str = None
        ocr_output_format: str = "json"
        ocr_max_tokens: int = 4096
        ocr_temperature: float = 0.1
        ocr_timeout: int = 120
        ocr_max_retries: int = 3
        ocr_concurrency: int = 2
        ocr_batch_size: int = 2
        ocr_batch_rest: float = 1.0
        ocr_resize_max: int = 2048
        ocr_image_format: str = "PNG"
        ocr_image_quality: int = 95
        ocr_page_anchor_enabled: bool = False

    config = TestConfig()

    # 创建转换器
    try:
        converter = OcrDirectAsyncConverter(config)
        print("✅ 转换器创建成功")
    except Exception as e:
        print(f"❌ 转换器创建失败: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 测试单张图片转换
    if not Path(TEST_IMAGE_PATH).exists():
        print(f"❌ 测试图片不存在: {TEST_IMAGE_PATH}")
        return False

    try:
        print(f"📄 转换图片: {TEST_IMAGE_PATH}")
        document = await converter(TEST_IMAGE_PATH)

        print(f"✅ 转换成功")
        print(f"  Pages: {len(document.pages)}")

        for i, page in enumerate(document.pages):
            print(f"  Page {i+1}: {len(page.structure)} blocks")

        return True

    except Exception as e:
        print(f"❌ 转换失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("\n" + "="*80)
    print("OCR Direct 功能测试")
    print("="*80)

    results = {}

    # 测试 1: OcrChandraService
    results["OcrChandraService"] = test_ocr_service()

    # 测试 2: OcrParser
    results["OcrParser"] = test_ocr_parser()

    # 测试 3: OcrDirectAsyncConverter
    results["OcrDirectAsyncConverter"] = asyncio.run(test_ocr_converter())

    # 总结
    print("\n" + "="*80)
    print("测试总结")
    print("="*80)

    for name, success in results.items():
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{status} {name}")

    all_passed = all(results.values())
    if all_passed:
        print("\n🎉 所有测试通过！")
    else:
        print("\n⚠️ 部分测试失败，请检查错误信息")

    return all_passed


if __name__ == "__main__":
    main()
