"""
诊断脚本：检查 PageNumberProcessor 是否正确集成

运行此脚本可以快速诊断印刷页码提取功能的状态
"""

def check_page_number_processor():
    """检查 PageNumberProcessor 是否已集成"""
    print("=" * 60)
    print("检查 PageNumberProcessor 集成状态")
    print("=" * 60)

    try:
        # 检查 1: 是否可以导入
        print("\n[1] 检查导入...")
        from aih_contexture.processors.page_number import PageNumberProcessor
        print("    [OK] PageNumberProcessor 可以导入")

        # 检查 2: 是否在 PdfConverter 中
        print("\n[2] 检查 PdfConverter 集成...")
        from aih_contexture.converters.pdf import PdfConverter

        processor_names = [p.__name__ for p in PdfConverter.default_processors]

        if "PageNumberProcessor" in processor_names:
            print("    [OK] PageNumberProcessor 在 default_processors 列表中")

            # 找到位置
            index = processor_names.index("PageNumberProcessor")
            print(f"    位置: 第 {index + 1} 个处理器")

            # 显示前后的处理器
            if index > 0:
                print(f"    前一个: {processor_names[index - 1]}")
            if index < len(processor_names) - 1:
                print(f"    后一个: {processor_names[index + 1]}")
        else:
            print("    [FAIL] PageNumberProcessor 不在 default_processors 列表中")
            print("    这是根本原因！需要添加到列表中。")
            return False

        # 检查 3: 默认配置
        print("\n[3] 检查默认配置...")
        processor = PageNumberProcessor()
        print(f"    page_numbering_enabled: {processor.page_numbering_enabled}")
        print(f"    use_printed_page_number: {processor.use_printed_page_number}")

        if not processor.use_printed_page_number:
            print("    [WARNING] use_printed_page_number 默认为 False")
            print("    需要在配置中设置为 True，或在 UI 中勾选'提取印刷页码'")

        # 检查 4: 配置传递测试
        print("\n[4] 测试配置传递...")
        test_config = {
            "use_printed_page_number": True,
            "page_numbering_enabled": True,
            "page_number_format": "auto",
        }
        processor = PageNumberProcessor(test_config)
        print(f"    page_numbering_enabled: {processor.page_numbering_enabled}")
        print(f"    use_printed_page_number: {processor.use_printed_page_number}")
        print(f"    page_number_format: {processor.page_number_format}")

        if processor.use_printed_page_number:
            print("    [OK] 配置传递正常")
        else:
            print("    [FAIL] 配置传递失败")

        return True

    except ImportError as e:
        print(f"    [FAIL] 导入失败: {e}")
        return False
    except Exception as e:
        print(f"    [FAIL] 检查失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_ui_configuration():
    """检查 UI 配置"""
    print("\n" + "=" * 60)
    print("UI 配置检查清单")
    print("=" * 60)

    print("\n请在 Streamlit UI 中检查以下配置：")
    print("\n[页码锚点配置]")
    print("  [ ] 启用页码锚点")
    print("  [ ] 提取印刷页码  ← 必须勾选！")
    print("\n[Pipeline 模式详细配置]（如果勾选了'提取印刷页码'）")
    print("  页码搜索区域: [页脚, 页眉]")
    print("  页码格式: 自动检测")
    print("  页眉结束位置: 0.15")
    print("  页脚起始位置: 0.83")
    print("\n[OCR 配置]")
    print("  如果 PDF 有文本层:")
    print("    OCR 后端: 禁用")
    print("    （确保 use_pdf_text=True）")
    print("  如果 PDF 是扫描件:")
    print("    OCR 后端: Surya OCR  ← 必须启用！")


def check_pdf_text_layer():
    """检查 PDF 文本层"""
    print("\n" + "=" * 60)
    print("PDF 文本层检查")
    print("=" * 60)

    print("\n如何检查 PDF 是否有文本层：")
    print("\n方法 1: 在 PDF 阅读器中")
    print("  1. 打开 PDF 文件")
    print("  2. 尝试选择文本（鼠标拖动）")
    print("  3. 如果可以选择 → 有文本层 ✓")
    print("  4. 如果不能选择 → 扫描件，无文本层 ✗")

    print("\n方法 2: 使用 Python")
    print("  ```python")
    print("  import pdfplumber")
    print("  with pdfplumber.open('your.pdf') as pdf:")
    print("      page = pdf.pages[0]")
    print("      text = page.extract_text()")
    print("      if text:")
    print("          print('有文本层')")
    print("      else:")
    print("          print('无文本层')")
    print("  ```")


def provide_solutions():
    """提供解决方案"""
    print("\n" + "=" * 60)
    print("解决方案")
    print("=" * 60)

    print("\n场景 1: PDF 有文本层")
    print("  配置:")
    print("    - OCR 后端: 禁用")
    print("    - ✅ 勾选'提取印刷页码'")
    print("    - 确保 use_pdf_text=True")
    print("  预期: 可以提取印刷页码")

    print("\n场景 2: PDF 是扫描件")
    print("  配置:")
    print("    - OCR 后端: Surya OCR  ← 必须启用")
    print("    - ✅ 勾选'提取印刷页码'")
    print("  预期: 可以提取印刷页码")

    print("\n场景 3: 无法提取页码")
    print("  配置:")
    print("    - OCR 后端: 禁用")
    print("    - ✗ 不勾选'提取印刷页码'")
    print("    - 自定义编号来源: 自动生成")
    print("  预期: 使用自定义编号")


if __name__ == "__main__":
    print("Surya + 禁用 OCR 印刷页码诊断工具")
    print("=" * 60)

    # 运行检查
    success = check_page_number_processor()

    if success:
        check_ui_configuration()
        check_pdf_text_layer()
        provide_solutions()

        print("\n" + "=" * 60)
        print("诊断完成")
        print("=" * 60)

        print("\n最可能的原因:")
        print("1. 未勾选'提取印刷页码'复选框")
        print("2. PDF 无文本层 + 禁用 OCR")
        print("3. 页码不在搜索区域内")

        print("\n快速解决:")
        print("1. 在 UI 中勾选'提取印刷页码'")
        print("2. 如果 PDF 是扫描件，启用 OCR")
        print("3. 如果无法提取，使用自定义编号")
    else:
        print("\n" + "=" * 60)
        print("发现严重问题")
        print("=" * 60)
        print("\nPageNumberProcessor 未正确集成到 PdfConverter")
        print("请检查 marker/converters/pdf.py 文件")
