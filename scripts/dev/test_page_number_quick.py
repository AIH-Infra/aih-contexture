"""
快速测试印刷页码提取
"""

import sys
import logging

# 设置日志级别
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

from aih_contexture.converters.pdf import PdfConverter
from aih_contexture.models import create_model_dict

def test_page_number_extraction(pdf_path):
    print("=" * 80)
    print("快速测试印刷页码提取")
    print("=" * 80)
    print(f"PDF: {pdf_path}")
    print()

    # 配置
    config = {
        "layout_backend": "surya",
        "ocr_backend": "surya",
        "disable_ocr": True,  # 禁用 OCR（测试原生 PDF）
        "page_range": [0, 1, 2],  # 只处理前 3 页
        "page_numbering_enabled": True,
        "use_printed_page_number": True,
        "printed_page_zones": ["footer", "header"],
        "page_number_format": "auto",
    }

    print("配置:")
    for key, value in config.items():
        print(f"  {key}: {value}")
    print()

    # 创建模型
    print("加载模型...")
    model_dict = create_model_dict()

    # 创建转换器
    print("创建转换器...")
    converter = PdfConverter(
        artifact_dict=model_dict,
        config=config
    )

    # 转换
    print()
    print("=" * 80)
    print("开始转换...")
    print("=" * 80)
    print()

    result = converter(pdf_path)

    print()
    print("=" * 80)
    print("转换完成")
    print("=" * 80)
    print()

    # 检查结果
    markdown = str(result)

    # 检查页码标签
    import re
    page_tags = re.findall(r"<!-- Page: ([^>]+) -->", markdown)

    if page_tags:
        print(f"✅ 找到 {len(page_tags)} 个印刷页码标签:")
        for i, tag in enumerate(page_tags):
            print(f"  页面 {i}: <!-- Page: {tag} -->")
    else:
        print("❌ 未找到印刷页码标签")

    # 显示前 500 字符
    print()
    print("输出预览（前 500 字符）:")
    print("-" * 80)
    print(markdown[:500])
    print("-" * 80)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用方法: python test_page_number_quick.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    test_page_number_extraction(pdf_path)
