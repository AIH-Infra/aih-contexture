"""
简化测试：验证新增的 BlockTypes

只测试 BlockTypes 枚举，不需要其他依赖
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))


def main():
    print("\n" + "=" * 60)
    print("Marginal Annotation - BlockTypes Verification")
    print("=" * 60 + "\n")

    try:
        from aih_contexture.schema import BlockTypes

        # 检查新类型是否存在
        print("Checking new BlockTypes...")
        assert hasattr(BlockTypes, 'MarginalAnnotation'), "MarginalAnnotation not found"
        assert hasattr(BlockTypes, 'InlineAnnotation'), "InlineAnnotation not found"
        print("[OK] MarginalAnnotation exists in BlockTypes")
        print("[OK] InlineAnnotation exists in BlockTypes")

        # 检查字符串表示
        print("\nChecking string representation...")
        assert str(BlockTypes.MarginalAnnotation) == "MarginalAnnotation"
        assert str(BlockTypes.InlineAnnotation) == "InlineAnnotation"
        print("[OK] String representation correct")

        # 列出所有 BlockTypes
        print("\nAll BlockTypes:")
        all_types = [bt.name for bt in BlockTypes]
        for i, bt in enumerate(all_types, 1):
            marker = " <-- NEW" if bt in ["MarginalAnnotation", "InlineAnnotation"] else ""
            print(f"  {i:2d}. {bt}{marker}")

        print(f"\nTotal: {len(all_types)} block types")

        print("\n" + "=" * 60)
        print("[SUCCESS] BlockTypes verification passed!")
        print("=" * 60)
        print("\nNew block types added:")
        print("  1. MarginalAnnotation - For marginal notes, page numbers, line numbers")
        print("  2. InlineAnnotation - For inline small-text annotations")
        print()

        return 0

    except Exception as e:
        print(f"\n[FAILED] Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
