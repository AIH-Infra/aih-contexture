"""
测试新增的边码识别功能

测试内容：
1. 验证新的 BlockTypes 是否正确注册
2. 验证块类是否可以正确实例化
3. 验证 Processor 是否可以正确导入和初始化
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def test_block_types():
    """测试 BlockTypes 枚举"""
    print("=" * 60)
    print("Test 1: BlockTypes Enum")
    print("=" * 60)

    from aih_contexture.schema import BlockTypes

    # 检查新类型是否存在
    assert hasattr(BlockTypes, 'MarginalAnnotation'), "MarginalAnnotation 未在 BlockTypes 中定义"
    assert hasattr(BlockTypes, 'InlineAnnotation'), "InlineAnnotation 未在 BlockTypes 中定义"

    print("[OK] MarginalAnnotation added to BlockTypes")
    print("[OK] InlineAnnotation added to BlockTypes")

    # 检查字符串表示
    assert str(BlockTypes.MarginalAnnotation) == "MarginalAnnotation"
    assert str(BlockTypes.InlineAnnotation) == "InlineAnnotation"

    print("[OK] BlockTypes string representation correct")
    print()


def test_supported_labels():
    """测试 SUPPORTED_LAYOUT_LABELS"""
    print("=" * 60)
    print("Test 2: SUPPORTED_LAYOUT_LABELS")
    print("=" * 60)

    from aih_contexture.services.layout_base import SUPPORTED_LAYOUT_LABELS

    assert "MarginalAnnotation" in SUPPORTED_LAYOUT_LABELS, "MarginalAnnotation 未在 SUPPORTED_LAYOUT_LABELS 中"
    assert "InlineAnnotation" in SUPPORTED_LAYOUT_LABELS, "InlineAnnotation 未在 SUPPORTED_LAYOUT_LABELS 中"

    print("[OK] MarginalAnnotation added to SUPPORTED_LAYOUT_LABELS")
    print("[OK] InlineAnnotation added to SUPPORTED_LAYOUT_LABELS")
    print(f"   Total supported labels: {len(SUPPORTED_LAYOUT_LABELS)}")
    print()


def test_block_classes():
    """测试块类"""
    print("=" * 60)
    print("Test 3: Block Class Instantiation")
    print("=" * 60)

    from aih_contexture.schema.blocks.marginalannotation import MarginalAnnotation
    from aih_contexture.schema.blocks.inlineannotation import InlineAnnotation
    from aih_contexture.schema import BlockTypes

    # 测试 MarginalAnnotation
    marginal = MarginalAnnotation(
        polygon=[[0, 0], [100, 0], [100, 50], [0, 50]],
        block_description="Test marginal annotation"
    )
    assert marginal.block_type == BlockTypes.MarginalAnnotation
    print("[OK] MarginalAnnotation class instantiated correctly")

    # 测试 InlineAnnotation
    inline = InlineAnnotation(
        polygon=[[0, 0], [100, 0], [100, 50], [0, 50]],
        block_description="Test inline annotation"
    )
    assert inline.block_type == BlockTypes.InlineAnnotation
    print("[OK] InlineAnnotation class instantiated correctly")
    print()


def test_registry():
    """测试注册表"""
    print("=" * 60)
    print("Test 4: Block Class Registry")
    print("=" * 60)

    from aih_contexture.schema.registry import get_block_class, BLOCK_REGISTRY
    from aih_contexture.schema import BlockTypes

    # 检查是否已注册
    assert BlockTypes.MarginalAnnotation in BLOCK_REGISTRY, "MarginalAnnotation 未注册"
    assert BlockTypes.InlineAnnotation in BLOCK_REGISTRY, "InlineAnnotation 未注册"

    print("[OK] MarginalAnnotation registered")
    print("[OK] InlineAnnotation registered")

    # 测试获取块类
    marginal_cls = get_block_class(BlockTypes.MarginalAnnotation)
    inline_cls = get_block_class(BlockTypes.InlineAnnotation)

    assert marginal_cls.__name__ == "MarginalAnnotation"
    assert inline_cls.__name__ == "InlineAnnotation"

    print("[OK] Can retrieve block classes via get_block_class")
    print(f"   Total registered block types: {len(BLOCK_REGISTRY)}")
    print()


def test_processors():
    """测试处理器"""
    print("=" * 60)
    print("Test 5: Processors")
    print("=" * 60)

    from aih_contexture.processors.marginal_annotation import MarginalAnnotationProcessor
    from aih_contexture.processors.inline_annotation import InlineAnnotationProcessor

    # 测试 MarginalAnnotationProcessor
    marginal_processor = MarginalAnnotationProcessor()
    assert marginal_processor.enable_marginal_detection == True
    print("[OK] MarginalAnnotationProcessor initialized correctly")
    print(f"   - Left margin threshold: {marginal_processor.left_margin_threshold}")
    print(f"   - Right margin threshold: {marginal_processor.right_margin_threshold}")
    print(f"   - Top margin threshold: {marginal_processor.top_margin_threshold}")

    # 测试 InlineAnnotationProcessor
    inline_processor = InlineAnnotationProcessor()
    assert inline_processor.enable_inline_detection == True
    print("[OK] InlineAnnotationProcessor initialized correctly")
    print(f"   - Font size ratio threshold: {inline_processor.font_size_ratio_threshold}")
    print(f"   - Max annotation length: {inline_processor.max_inline_annotation_length}")
    print()


def test_html_rendering():
    """测试 HTML 渲染"""
    print("=" * 60)
    print("Test 6: HTML Rendering")
    print("=" * 60)

    from aih_contexture.schema.blocks.marginalannotation import MarginalAnnotation
    from aih_contexture.schema.blocks.inlineannotation import InlineAnnotation
    from aih_contexture.schema.document import Document

    # 创建测试块
    marginal = MarginalAnnotation(
        polygon=[[0, 0], [100, 0], [100, 50], [0, 50]],
        block_description="Test marginal",
        page_id=0,
        block_id=1
    )
    marginal.set_internal_metadata("marginal_subtype", "行号")
    marginal.set_internal_metadata("position_type", "left_margin")

    # 测试 HTML 输出
    html = marginal.assemble_html(None, [], None, None)
    assert 'class="marginal-annotation"' in html
    assert 'data-subtype="行号"' in html
    assert 'data-position="left_margin"' in html
    print("[OK] MarginalAnnotation HTML rendering correct")
    print(f"   HTML: {html[:100]}...")

    # 测试 InlineAnnotation
    inline = InlineAnnotation(
        polygon=[[0, 0], [100, 0], [100, 50], [0, 50]],
        block_description="Test inline",
        page_id=0,
        block_id=2
    )
    inline.set_internal_metadata("inline_subtype", "夹注")
    inline.set_internal_metadata("font_size_ratio", 0.65)

    html = inline.assemble_html(None, [], None, None)
    assert 'class="inline-annotation"' in html
    assert 'data-subtype="夹注"' in html
    assert 'data-font-ratio="0.65"' in html
    print("[OK] InlineAnnotation HTML rendering correct")
    print(f"   HTML: {html[:100]}...")
    print()


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("Marginal Annotation Feature Tests")
    print("=" * 60 + "\n")

    try:
        test_block_types()
        test_supported_labels()
        test_block_classes()
        test_registry()
        test_processors()
        test_html_rendering()

        print("=" * 60)
        print("[SUCCESS] All tests passed!")
        print("=" * 60)
        print("\nNew features summary:")
        print("  1. Added MarginalAnnotation block type")
        print("  2. Added InlineAnnotation block type")
        print("  3. Implemented MarginalAnnotationProcessor")
        print("  4. Implemented InlineAnnotationProcessor")
        print("\nSupported marginal annotation types:")
        print("  - Page numbers (Chinese classics)")
        print("  - Fish-tail decorations")
        print("  - Stephanus numbers (Plato)")
        print("  - Bekker numbers (Aristotle)")
        print("  - Line numbers (Critical editions)")
        print("  - Book ears")
        print("  - Marginal notes")
        print("\nSupported inline annotation types:")
        print("  - Double-line small text")
        print("  - Interlinear notes")
        print("  - Split annotations")
        print("  - Parenthetical notes")
        print()

        return 0

    except Exception as e:
        print(f"\n[FAILED] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
