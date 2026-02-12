"""
测试VLM模式的多格式输出功能

演示如何使用VlmDirectAsyncConverter配合不同的渲染器输出多种格式。
"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

from aih_contexture.converters.vlm_direct_async import VlmDirectAsyncConverter
from aih_contexture.output import save_output


def test_markdown_output():
    """测试1: 默认Markdown输出 (向后兼容)"""
    print("\n" + "="*60)
    print("测试1: 默认Markdown输出")
    print("="*60)

    config = {
        "vlm_direct_base_url": "https://api.openai.com/v1",
        "vlm_direct_model": "gpt-4o",
        "vlm_direct_api_key": os.getenv("OPENAI_API_KEY", ""),
        "vlm_direct_max_concurrent": 3,
    }

    converter = VlmDirectAsyncConverter(config)
    result = converter("test.pdf")

    print(f"输出类型: {type(result)}")
    print(f"输出长度: {len(result)} 字符")
    print(f"前100字符: {result[:100]}...")

    # 保存为文件
    with open("output_markdown.md", "w", encoding="utf-8") as f:
        f.write(result)
    print("✓ 已保存到 output_markdown.md")


def test_markdown_renderer():
    """测试2: 使用MarkdownRenderer输出 (带元数据)"""
    print("\n" + "="*60)
    print("测试2: MarkdownRenderer输出 (带元数据)")
    print("="*60)

    config = {
        "vlm_direct_base_url": "https://api.openai.com/v1",
        "vlm_direct_model": "gpt-4o",
        "vlm_direct_api_key": os.getenv("OPENAI_API_KEY", ""),
        "vlm_direct_max_concurrent": 3,
        "renderer": "marker.renderers.markdown.MarkdownRenderer",
    }

    converter = VlmDirectAsyncConverter(config)
    result = converter("test.pdf")

    print(f"输出类型: {type(result)}")
    print(f"输出类名: {type(result).__name__}")
    print(f"Markdown长度: {len(result.markdown)} 字符")
    print(f"元数据: {result.metadata}")
    print(f"图像数量: {len(result.images)}")

    # 使用save_output保存
    save_output(result, ".", "output_markdown_renderer")
    print("✓ 已保存到 output_markdown_renderer.md 和 output_markdown_renderer_meta.json")


def test_html_renderer():
    """测试3: 使用HTMLRenderer输出"""
    print("\n" + "="*60)
    print("测试3: HTMLRenderer输出")
    print("="*60)

    config = {
        "vlm_direct_base_url": "https://api.openai.com/v1",
        "vlm_direct_model": "gpt-4o",
        "vlm_direct_api_key": os.getenv("OPENAI_API_KEY", ""),
        "vlm_direct_max_concurrent": 3,
        "renderer": "marker.renderers.html.HTMLRenderer",
    }

    converter = VlmDirectAsyncConverter(config)
    result = converter("test.pdf")

    print(f"输出类型: {type(result)}")
    print(f"输出类名: {type(result).__name__}")
    print(f"HTML长度: {len(result.html)} 字符")
    print(f"元数据: {result.metadata}")

    # 使用save_output保存
    save_output(result, ".", "output_html")
    print("✓ 已保存到 output_html.html 和 output_html_meta.json")


def test_json_renderer():
    """测试4: 使用JSONRenderer输出"""
    print("\n" + "="*60)
    print("测试4: JSONRenderer输出 (结构化)")
    print("="*60)

    config = {
        "vlm_direct_base_url": "https://api.openai.com/v1",
        "vlm_direct_model": "gpt-4o",
        "vlm_direct_api_key": os.getenv("OPENAI_API_KEY", ""),
        "vlm_direct_max_concurrent": 3,
        "renderer": "marker.renderers.json.JSONRenderer",
    }

    converter = VlmDirectAsyncConverter(config)
    result = converter("test.pdf")

    print(f"输出类型: {type(result)}")
    print(f"输出类名: {type(result).__name__}")
    print(f"Block类型: {result.block_type}")
    print(f"子Block数量: {len(result.children)}")
    print(f"元数据: {result.metadata}")

    # 使用save_output保存
    save_output(result, ".", "output_json")
    print("✓ 已保存到 output_json.json 和 output_json_meta.json")


def test_chunk_renderer():
    """测试5: 使用ChunkRenderer输出 (适合RAG)"""
    print("\n" + "="*60)
    print("测试5: ChunkRenderer输出 (适合RAG)")
    print("="*60)

    config = {
        "vlm_direct_base_url": "https://api.openai.com/v1",
        "vlm_direct_model": "gpt-4o",
        "vlm_direct_api_key": os.getenv("OPENAI_API_KEY", ""),
        "vlm_direct_max_concurrent": 3,
        "renderer": "marker.renderers.chunk.ChunkRenderer",
    }

    converter = VlmDirectAsyncConverter(config)
    result = converter("test.pdf")

    print(f"输出类型: {type(result)}")
    print(f"输出类名: {type(result).__name__}")
    print(f"Block数量: {len(result.blocks)}")
    print(f"页面信息: {result.page_info}")
    print(f"元数据: {result.metadata}")

    # 使用save_output保存
    save_output(result, ".", "output_chunks")
    print("✓ 已保存到 output_chunks.json 和 output_chunks_meta.json")


def main():
    """运行所有测试"""
    print("\n" + "="*60)
    print("VLM多格式输出测试")
    print("="*60)

    # 检查API密钥
    if not os.getenv("OPENAI_API_KEY"):
        print("⚠ 警告: 未设置 OPENAI_API_KEY 环境变量")
        print("请设置: export OPENAI_API_KEY='your-key-here'")
        return

    # 检查测试文件
    if not os.path.exists("test.pdf"):
        print("⚠ 警告: 未找到 test.pdf 文件")
        print("请将测试PDF文件命名为 test.pdf 并放在当前目录")
        return

    try:
        # 运行所有测试
        test_markdown_output()
        test_markdown_renderer()
        test_html_renderer()
        test_json_renderer()
        test_chunk_renderer()

        print("\n" + "="*60)
        print("✓ 所有测试完成!")
        print("="*60)
        print("\n生成的文件:")
        print("- output_markdown.md (纯Markdown)")
        print("- output_markdown_renderer.md + _meta.json (Markdown + 元数据)")
        print("- output_html.html + _meta.json (HTML)")
        print("- output_json.json + _meta.json (结构化JSON)")
        print("- output_chunks.json + _meta.json (分块JSON, 适合RAG)")

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
