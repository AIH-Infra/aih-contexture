"""
VLM多格式输出 - 简单示例

演示如何使用VLM模式输出不同格式。
"""

import os
from aih_contexture.converters.vlm_direct_async import VlmDirectAsyncConverter
from aih_contexture.output import save_output


def example_basic():
    """示例1: 基础用法 - 返回Markdown字符串"""
    print("\n=== 示例1: 基础用法 ===")

    config = {
        "vlm_direct_api_key": os.getenv("OPENAI_API_KEY"),
        "vlm_direct_model": "gpt-4o",
    }

    converter = VlmDirectAsyncConverter(config)
    result = converter("test.pdf")

    print(f"类型: {type(result)}")  # <class 'str'>
    print(f"长度: {len(result)} 字符")
    print(f"预览: {result[:200]}...")


def example_with_renderer():
    """示例2: 使用渲染器 - 返回结构化对象"""
    print("\n=== 示例2: 使用渲染器 ===")

    config = {
        "vlm_direct_api_key": os.getenv("OPENAI_API_KEY"),
        "vlm_direct_model": "gpt-4o",
        "renderer": "marker.renderers.markdown.MarkdownRenderer",
    }

    converter = VlmDirectAsyncConverter(config)
    result = converter("test.pdf")

    print(f"类型: {type(result).__name__}")  # MarkdownOutput
    print(f"Markdown长度: {len(result.markdown)} 字符")
    print(f"元数据: {result.metadata}")

    # 保存
    save_output(result, ".", "output")
    print("✓ 已保存到 output.md 和 output_meta.json")


def example_json():
    """示例3: JSON输出 - 结构化数据"""
    print("\n=== 示例3: JSON输出 ===")

    config = {
        "vlm_direct_api_key": os.getenv("OPENAI_API_KEY"),
        "vlm_direct_model": "gpt-4o",
        "renderer": "marker.renderers.json.JSONRenderer",
    }

    converter = VlmDirectAsyncConverter(config)
    result = converter("test.pdf")

    print(f"类型: {type(result).__name__}")  # JSONOutput
    print(f"Block类型: {result.block_type}")
    print(f"子Block数: {len(result.children)}")

    # 遍历Block
    for i, block in enumerate(result.children[:3]):  # 只显示前3个
        print(f"\nBlock {i}:")
        print(f"  ID: {block.id}")
        print(f"  类型: {block.block_type}")
        print(f"  HTML: {block.html[:100]}...")

    # 保存
    save_output(result, ".", "output_json")
    print("\n✓ 已保存到 output_json.json")


def example_html():
    """示例4: HTML输出 - 网页格式"""
    print("\n=== 示例4: HTML输出 ===")

    config = {
        "vlm_direct_api_key": os.getenv("OPENAI_API_KEY"),
        "vlm_direct_model": "gpt-4o",
        "renderer": "marker.renderers.html.HTMLRenderer",
    }

    converter = VlmDirectAsyncConverter(config)
    result = converter("test.pdf")

    print(f"类型: {type(result).__name__}")  # HTMLOutput
    print(f"HTML长度: {len(result.html)} 字符")
    print(f"预览: {result.html[:200]}...")

    # 保存
    save_output(result, ".", "output_html")
    print("\n✓ 已保存到 output_html.html")


def example_chunks():
    """示例5: Chunks输出 - 适合RAG"""
    print("\n=== 示例5: Chunks输出 (RAG) ===")

    config = {
        "vlm_direct_api_key": os.getenv("OPENAI_API_KEY"),
        "vlm_direct_model": "gpt-4o",
        "renderer": "marker.renderers.chunk.ChunkRenderer",
    }

    converter = VlmDirectAsyncConverter(config)
    result = converter("test.pdf")

    print(f"类型: {type(result).__name__}")  # ChunkOutput
    print(f"Block数: {len(result.blocks)}")
    print(f"页面数: {len(result.page_info)}")

    # 显示前3个chunk
    for i, block in enumerate(result.blocks[:3]):
        print(f"\nChunk {i}:")
        print(f"  ID: {block.id}")
        print(f"  页码: {block.page}")
        print(f"  类型: {block.block_type}")
        print(f"  HTML: {block.html[:100]}...")

    # 保存
    save_output(result, ".", "output_chunks")
    print("\n✓ 已保存到 output_chunks.json")


if __name__ == "__main__":
    print("VLM多格式输出示例")
    print("=" * 60)

    # 检查API密钥
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠ 请设置 OPENAI_API_KEY 环境变量")
        print("export OPENAI_API_KEY='sk-...'")
        exit(1)

    # 检查测试文件
    if not os.path.exists("test.pdf"):
        print("⚠ 请准备测试文件 test.pdf")
        exit(1)

    # 运行示例 (选择一个)
    # example_basic()
    # example_with_renderer()
    # example_json()
    # example_html()
    example_chunks()

    print("\n" + "=" * 60)
    print("✓ 完成!")
