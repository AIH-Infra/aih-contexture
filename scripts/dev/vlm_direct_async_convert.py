"""
VLM Direct Async 转换脚本 - 异步并发版本

完全跳过 Surya，纯用 VLM 处理，支持多线程并发。

使用示例：
    # 基本使用（默认 5 并发）
    python vlm_direct_async_convert.py input.pdf --api-key sk-xxx

    # 高并发（10 线程）
    python vlm_direct_async_convert.py input.pdf --api-key sk-xxx --concurrent 10

    # 低并发（2 线程，适合免费 API）
    python vlm_direct_async_convert.py input.pdf --api-key sk-xxx --concurrent 2

性能对比：
    - 串行：25页 × 10秒 = 4-8分钟
    - 并发5：25页 ÷ 5 = 1-2分钟（提速 5倍）
    - 并发10：25页 ÷ 10 = 0.5-1分钟（提速 10倍）
"""

import argparse
import sys
from pathlib import Path

from aih_contexture.converters.vlm_direct_async import VlmDirectAsyncConverter
from aih_contexture.logger import get_logger

logger = get_logger()


def main():
    parser = argparse.ArgumentParser(
        description="VLM Direct Async Converter - 异步并发版本，完全跳过 Surya"
    )

    # 输入输出
    parser.add_argument("input", type=str, help="输入文件路径（PDF, 图片等）")
    parser.add_argument("--output", "-o", type=str, help="输出 Markdown 文件路径（默认：input.md）")

    # API 配置
    parser.add_argument("--base-url", type=str, default="https://api.openai.com/v1",
                        help="API Base URL（默认：OpenAI）")
    parser.add_argument("--model", type=str, default="gpt-4o",
                        help="模型名称（默认：gpt-4o）")
    parser.add_argument("--api-key", type=str, default="",
                        help="API 密钥")

    # 并发配置（新增）
    parser.add_argument("--concurrent", "-c", type=int, default=5,
                        help="最大并发数（默认：5，推荐 2-10）")

    # 图像配置
    parser.add_argument("--image-format", type=str, default="jpeg", choices=["jpeg", "png", "webp"],
                        help="图像格式（默认：jpeg）")
    parser.add_argument("--max-dimension", type=int, default=2048,
                        help="图像最大边长（默认：2048）")
    parser.add_argument("--jpeg-quality", type=int, default=90,
                        help="JPEG 质量（默认：90）")

    # API 调用配置
    parser.add_argument("--timeout", type=int, default=180,
                        help="API 超时时间（秒，默认：180）")
    parser.add_argument("--max-tokens", type=int, default=8192,
                        help="最大输出 token 数（默认：8192）")
    parser.add_argument("--max-retries", type=int, default=3,
                        help="最大重试次数（默认：3）")

    # 提示词
    parser.add_argument("--prompt", type=str, default="",
                        help="自定义提示词（留空使用默认）")

    # 页面分隔符
    parser.add_argument("--page-separator", type=str, default="\n\n---\n\n",
                        help="页面分隔符（默认：\\n\\n---\\n\\n）")

    args = parser.parse_args()

    # 检查输入文件
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"输入文件不存在: {args.input}")
        sys.exit(1)

    # 确定输出路径
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_suffix(".md")

    # 构建配置
    config = {
        "vlm_direct_base_url": args.base_url,
        "vlm_direct_model": args.model,
        "vlm_direct_api_key": args.api_key,
        "vlm_direct_image_format": args.image_format,
        "vlm_direct_max_image_dimension": args.max_dimension,
        "vlm_direct_jpeg_quality": args.jpeg_quality,
        "vlm_direct_timeout": args.timeout,
        "vlm_direct_max_tokens": args.max_tokens,
        "vlm_direct_max_retries": args.max_retries,
        "vlm_direct_max_concurrent": args.concurrent,
        "vlm_direct_page_separator": args.page_separator,
    }

    if args.prompt:
        config["vlm_direct_prompt"] = args.prompt

    # 创建 converter
    logger.info("=" * 60)
    logger.info(f"输入文件: {input_path}")
    logger.info(f"输出文件: {output_path}")
    logger.info(f"模型: {args.model}")
    logger.info(f"并发数: {args.concurrent}")
    logger.info("=" * 60)

    converter = VlmDirectAsyncConverter(config)

    # 转换
    try:
        markdown = converter(str(input_path))

        # 保存结果
        output_path.write_text(markdown, encoding="utf-8")

        logger.info("=" * 60)
        logger.info(f"✅ 转换完成！")
        logger.info(f"📄 输出文件: {output_path}")
        logger.info(f"📊 总字符数: {len(markdown)}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"❌ 转换失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
