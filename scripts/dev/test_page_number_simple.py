"""
简化的页码提取测试脚本
直接测试 PDF 文本层和 Surya 布局识别
"""

import sys
import os

def test_pdf_text_layer(pdf_path):
    """测试 PDF 是否有文本层"""
    print("=" * 80)
    print("1. 测试 PDF 文本层")
    print("=" * 80)

    try:
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(pdf_path)
        print(f"✅ PDF 加载成功，共 {len(pdf)} 页")

        # 测试前 3 页
        for page_idx in range(min(3, len(pdf))):
            page = pdf[page_idx]
            textpage = page.get_textpage()
            text = textpage.get_text_range()

            print(f"\n页面 {page_idx + 1}:")
            print(f"  文本长度: {len(text)} 字符")
            if text.strip():
                print(f"  前 200 字符: {text[:200]}")

                # 检查是否包含数字（可能是页码）
                import re
                numbers = re.findall(r'\b\d+\b', text)
                if numbers:
                    print(f"  找到的数字: {numbers[:10]}")
            else:
                print(f"  ❌ 页面没有文本内容")

        pdf.close()
        return True

    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_surya_layout(pdf_path):
    """测试 Surya 布局识别"""
    print("\n" + "=" * 80)
    print("2. 测试 Surya 布局识别")
    print("=" * 80)

    try:
        from aih_contexture.models import create_model_dict
        from aih_contexture.providers.pdf import PdfProvider
        from PIL import Image

        print("✅ 正在加载模型...")
        model_dict = create_model_dict()
        layout_model = model_dict["layout"]
        print("✅ 模型加载成功")

        print("✅ 正在加载 PDF...")
        provider = PdfProvider(pdf_path, {"page_range": [0, 1, 2]})
        print(f"✅ PDF 加载成功，处理前 3 页")

        # 获取页面图像
        images = provider.get_images([0, 1, 2], dpi=96)
        print(f"✅ 获取了 {len(images)} 个页面图像")

        # 运行 Surya 布局检测
        print("✅ 正在运行 Surya 布局检测...")
        layout_results = layout_model(images, batch_size=1)
        print(f"✅ 布局检测完成")

        # 分析结果
        for page_idx, layout_result in enumerate(layout_results):
            print(f"\n页面 {page_idx + 1}:")
            print(f"  识别出 {len(layout_result.bboxes)} 个块")

            # 统计块类型
            block_types = {}
            for bbox in layout_result.bboxes:
                block_type = bbox.label
                block_types[block_type] = block_types.get(block_type, 0) + 1

            print(f"  块类型分布:")
            for block_type, count in sorted(block_types.items()):
                print(f"    {block_type}: {count}")

            # 检查是否有 PageHeader 或 PageFooter
            has_header = any(bbox.label == "PageHeader" for bbox in layout_result.bboxes)
            has_footer = any(bbox.label == "PageFooter" for bbox in layout_result.bboxes)

            if has_header:
                print(f"  ✅ 找到 PageHeader 块")
            else:
                print(f"  ❌ 没有找到 PageHeader 块")

            if has_footer:
                print(f"  ✅ 找到 PageFooter 块")
            else:
                print(f"  ❌ 没有找到 PageFooter 块")

        return True

    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    if len(sys.argv) < 2:
        print("使用方法: python test_page_number_simple.py <pdf_file_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]

    if not os.path.exists(pdf_path):
        print(f"❌ 错误: 文件不存在: {pdf_path}")
        sys.exit(1)

    print(f"测试文件: {pdf_path}")
    print()

    # 测试 1: PDF 文本层
    has_text = test_pdf_text_layer(pdf_path)

    # 测试 2: Surya 布局识别
    surya_ok = test_surya_layout(pdf_path)

    # 总结
    print("\n" + "=" * 80)
    print("测试总结")
    print("=" * 80)

    if has_text:
        print("✅ PDF 有文本层，可以提取文本")
    else:
        print("❌ PDF 没有文本层，需要启用 OCR")

    if surya_ok:
        print("✅ Surya 布局识别正常")
    else:
        print("❌ Surya 布局识别失败")

    print("\n关键问题:")
    print("1. Surya 是否识别出 PageHeader 或 PageFooter 块？")
    print("2. 如果没有，页码可能在其他类型的块中（如 Text 块）")
    print("3. 如果有，需要检查这些块是否包含文本内容")


if __name__ == "__main__":
    main()
