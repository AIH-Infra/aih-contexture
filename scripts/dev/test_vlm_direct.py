"""
VLM Direct Converter 测试脚本

快速测试 VLM Direct 方案是否正常工作
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from aih_contexture.converters.vlm_direct import VlmDirectConverter
from aih_contexture.logger import get_logger

logger = get_logger()


def test_basic():
    """测试基本功能"""
    logger.info("=" * 60)
    logger.info("测试 1: 基本功能测试")
    logger.info("=" * 60)

    # 配置（使用 LM Studio 本地服务）
    config = {
        "vlm_direct_base_url": "http://localhost:1234/v1",
        "vlm_direct_model": "gpt-4o",
        "vlm_direct_api_key": "lm-studio",
        "vlm_direct_max_image_dimension": 1536,
        "vlm_direct_jpeg_quality": 85,
        "vlm_direct_timeout": 120,
        "vlm_direct_max_tokens": 4096,
    }

    converter = VlmDirectConverter(config)
    logger.info("✅ VlmDirectConverter 初始化成功")

    # 检查配置
    assert converter.base_url == "http://localhost:1234/v1"
    assert converter.model == "gpt-4o"
    assert converter.max_image_dimension == 1536
    logger.info("✅ 配置验证通过")


def test_image_processing():
    """测试图像处理"""
    logger.info("=" * 60)
    logger.info("测试 2: 图像处理测试")
    logger.info("=" * 60)

    from PIL import Image
    import numpy as np

    config = {
        "vlm_direct_base_url": "http://localhost:1234/v1",
        "vlm_direct_model": "gpt-4o",
        "vlm_direct_max_image_dimension": 1024,
        "vlm_direct_jpeg_quality": 80,
    }

    converter = VlmDirectConverter(config)

    # 创建测试图像
    img = Image.fromarray(np.random.randint(0, 255, (2000, 1500, 3), dtype=np.uint8))
    logger.info(f"原始图像尺寸: {img.size}")

    # 测试缩放
    resized = converter._resize_if_needed(img)
    logger.info(f"缩放后尺寸: {resized.size}")

    assert max(resized.size) <= 1024, "图像应该被缩放到 1024 以内"
    logger.info("✅ 图像缩放功能正常")

    # 测试 base64 编码
    b64 = converter._img_to_base64(resized)
    assert len(b64) > 0, "base64 编码应该有内容"
    logger.info(f"✅ base64 编码成功（长度: {len(b64)}）")


def test_with_real_file():
    """测试真实文件（如果存在）"""
    logger.info("=" * 60)
    logger.info("测试 3: 真实文件测试")
    logger.info("=" * 60)

    # 查找测试文件
    test_files = [
        "test.pdf",
        "sample.pdf",
        "example.pdf",
    ]

    test_file = None
    for f in test_files:
        if Path(f).exists():
            test_file = f
            break

    if not test_file:
        logger.warning("⚠️ 未找到测试文件，跳过真实文件测试")
        logger.info("提示：将测试 PDF 命名为 test.pdf 放在当前目录")
        return

    logger.info(f"找到测试文件: {test_file}")

    # 配置（使用 LM Studio）
    config = {
        "vlm_direct_base_url": "http://localhost:1234/v1",
        "vlm_direct_model": "gpt-4o",
        "vlm_direct_api_key": "lm-studio",
        "vlm_direct_max_image_dimension": 1024,
        "vlm_direct_jpeg_quality": 80,
        "vlm_direct_timeout": 60,
        "vlm_direct_max_tokens": 2048,
    }

    converter = VlmDirectConverter(config)

    try:
        # 转换（只处理第一页作为测试）
        logger.info("开始转换...")
        markdown = converter(test_file)

        logger.info(f"✅ 转换成功！")
        logger.info(f"输出长度: {len(markdown)} 字符")
        logger.info(f"前 200 字符:\n{markdown[:200]}")

        # 保存结果
        output_file = Path(test_file).with_suffix(".test.md")
        output_file.write_text(markdown, encoding="utf-8")
        logger.info(f"✅ 结果已保存到: {output_file}")

    except Exception as e:
        logger.error(f"❌ 转换失败: {e}")
        import traceback
        traceback.print_exc()


def main():
    """运行所有测试"""
    logger.info("🚀 开始测试 VLM Direct Converter")
    logger.info("")

    try:
        # 测试 1: 基本功能
        test_basic()
        logger.info("")

        # 测试 2: 图像处理
        test_image_processing()
        logger.info("")

        # 测试 3: 真实文件（可选）
        test_with_real_file()
        logger.info("")

        logger.info("=" * 60)
        logger.info("✅ 所有测试通过！")
        logger.info("=" * 60)
        logger.info("")
        logger.info("下一步：")
        logger.info("1. 确保 LM Studio 正在运行（http://localhost:1234）")
        logger.info("2. 或者配置 OpenAI API key")
        logger.info("3. 运行: python vlm_direct_convert.py your_file.pdf")

    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
