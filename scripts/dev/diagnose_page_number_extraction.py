"""
快速诊断印刷页码提取问题

使用方法：
python diagnose_page_number_extraction.py <pdf_file_path>
"""

import sys
import os

# 设置日志级别为 DEBUG
os.environ["MARKER_DEBUG"] = "1"

from aih_contexture.converters.pdf import PdfConverter
from aih_contexture.models import create_model_dict
from aih_contexture.config.parser import ConfigParser
from aih_contexture.logger import get_logger
import logging

# 设置详细日志
logging.basicConfig(level=logging.DEBUG)
logger = get_logger()
logger.setLevel(logging.DEBUG)

# 设置 page_number 模块的日志级别
logging.getLogger("marker.processors.page_number").setLevel(logging.DEBUG)


def diagnose_pdf(pdf_path: str):
    """诊断 PDF 的页码提取问题"""

    print("=" * 80)
    print("印刷页码提取诊断工具")
    print("=" * 80)
    print(f"PDF 文件: {pdf_path}")
    print()

    if not os.path.exists(pdf_path):
        print(f"❌ 错误: 文件不存在: {pdf_path}")
        return

    # 配置
    config = {
        "layout_backend": "surya",  # 使用 Surya 布局检测
        "ocr_backend": "surya",     # 使用 Surya OCR
        "disable_ocr": True,        # 禁用 OCR（测试原生 PDF）
        "page_numbering_enabled": True,  # 启用页码处理
        "use_printed_page_number": True,  # 提取印刷页码
        "printed_page_zones": ["footer", "header"],  # 搜索区域
        "page_number_format": "arabic",  # 页码格式
    }

    print("配置:")
    for key, value in config.items():
        print(f"  {key}: {value}")
    print()

    # 创建模型
    print("正在加载模型...")
    try:
        model_dict = create_model_dict()
        print("✅ 模型加载成功")
    except Exception as e:
        print(f"❌ 模型加载失败: {e}")
        return

    # 创建转换器
    print("正在创建转换器...")
    try:
        converter = PdfConverter(
            artifact_dict=model_dict,
            config=config
        )
        print("✅ 转换器创建成功")
    except Exception as e:
        print(f"❌ 转换器创建失败: {e}")
        import traceback
        traceback.print_exc()
        return

    # 转换文档
    print()
    print("=" * 80)
    print("开始转换（只处理前 3 页）...")
    print("=" * 80)
    print()

    try:
        # 只处理前 3 页
        config["page_range"] = [0, 1, 2]
        converter.config = config

        result = converter(pdf_path)

        print()
        print("=" * 80)
        print("转换完成")
        print("=" * 80)
        print()

        # 检查结果
        if hasattr(result, "metadata"):
            print("元数据:")
            print(result.metadata)

        # 检查是否有页码标签
        markdown = str(result)
        if "<!-- Page:" in markdown:
            print("✅ 找到印刷页码标签!")
            # 提取所有页码标签
            import re
            page_tags = re.findall(r"<!-- Page: ([^>]+) -->", markdown)
            print(f"   提取的页码: {page_tags}")
        else:
            print("❌ 未找到印刷页码标签")

        # 显示前 500 个字符
        print()
        print("输出预览（前 500 字符）:")
        print("-" * 80)
        print(markdown[:500])
        print("-" * 80)

    except Exception as e:
        print(f"❌ 转换失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("使用方法: python diagnose_page_number_extraction.py <pdf_file_path>")
        print()
        print("示例:")
        print("  python diagnose_page_number_extraction.py test.pdf")
        sys.exit(1)

    pdf_path = sys.argv[1]
    diagnose_pdf(pdf_path)
