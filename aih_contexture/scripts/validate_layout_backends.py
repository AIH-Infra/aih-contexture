"""
端到端验证脚本：测试 Layout 后端的坐标系和 Structure 注入

验证目标：
1. Layout 输出的 LayoutResult/LayoutBox 格式正确
2. 坐标系转换（layout 图像坐标 → provider 页坐标）正确
3. Structure 正确注入到 page.structure
4. Blocks 的 polygon 落在页面 bbox 内
5. LineBuilder 对 layout 的 coverage 检查不崩溃

使用方法：
    python validate_layout_backends.py [test_pdf_path]

如果未提供 PDF，脚本将创建一个简单的测试 PDF。
"""

import os
import sys
import tempfile
from pathlib import Path

# 添加 marker 到路径
REPO_ROOT = str(Path(__file__).resolve().parents[2])
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

print(f"[Validator] Using marker from: {REPO_ROOT}")


def create_test_pdf() -> str:
    """创建一个简单的测试 PDF"""
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except ImportError:
        print("[Validator] ❌ reportlab not installed, cannot create test PDF")
        print("[Validator] Install: pip install reportlab")
        return None

    tmp_path = os.path.join(tempfile.gettempdir(), "marker_layout_test.pdf")
    c = canvas.Canvas(tmp_path, pagesize=letter)
    width, height = letter

    # 页面 1：简单文本
    c.setFont("Helvetica", 14)
    c.drawString(100, height - 100, "Marker Layout Backend Validation Test")
    c.drawString(100, height - 130, "This is a test document with multiple layout regions.")

    c.setFont("Helvetica", 12)
    c.drawString(100, height - 180, "Section 1: Introduction")
    c.drawString(100, height - 210, "Lorem ipsum dolor sit amet, consectetur adipiscing elit.")

    c.drawString(100, height - 260, "Section 2: Content")
    c.drawString(100, height - 290, "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.")

    # 绘制一个简单的矩形（模拟图片）
    c.setStrokeColorRGB(0, 0, 1)
    c.setFillColorRGB(0.8, 0.8, 1)
    c.rect(100, height - 450, 200, 100, fill=1)
    c.setFillColorRGB(0, 0, 0)
    c.drawString(150, height - 395, "[Figure]")

    c.showPage()
    c.save()

    print(f"[Validator] ✅ Created test PDF: {tmp_path}")
    return tmp_path


def validate_layout_structure(document, backend_name: str):
    """
    验证文档的 layout structure 是否正确。

    检查项：
    1. 每个页面都有 structure
    2. Structure 中的 blocks 存在于 document
    3. Blocks 的 polygon 坐标在页面范围内
    4. Blocks 有 block_type 和 top_k 属性
    """
    print(f"\n[Validator] Validating layout structure for backend: {backend_name}")

    if not document.pages:
        print("[Validator] ❌ No pages in document")
        return False

    all_checks_passed = True

    for page_idx, page in enumerate(document.pages):
        page_id = page.page_id
        page_bbox = page.polygon.bbox
        page_width = page_bbox[2] - page_bbox[0]
        page_height = page_bbox[3] - page_bbox[1]

        print(f"\n[Validator] Page {page_idx + 1} (ID: {page_id})")
        print(f"  Page size: {page_width:.1f} x {page_height:.1f}")

        # 检查 1: 页面是否有 structure
        if not hasattr(page, "structure") or page.structure is None:
            print(f"  ❌ Page has no structure attribute")
            all_checks_passed = False
            continue

        if not page.structure:
            print(f"  ⚠️  Page structure is empty (may be blank page)")
            continue

        print(f"  ✅ Page has {len(page.structure)} layout blocks")

        # 检查 2: Structure 中的每个 block
        for block_idx, block_id in enumerate(page.structure):
            try:
                block = document.get_block(block_id)
            except Exception as e:
                print(f"    ❌ Block {block_idx} (ID: {block_id}) not found: {e}")
                all_checks_passed = False
                continue

            # 检查 3: Block 的 block_type
            if not hasattr(block, "block_type"):
                print(f"    ❌ Block {block_idx} has no block_type")
                all_checks_passed = False
                continue

            # 检查 4: Block 的 polygon 坐标
            if not hasattr(block, "polygon"):
                print(f"    ❌ Block {block_idx} has no polygon")
                all_checks_passed = False
                continue

            block_bbox = block.polygon.bbox
            x1, y1, x2, y2 = block_bbox

            # 检查坐标是否在页面范围内（允许小误差）
            margin = 5  # 允许 5 像素的误差
            if x1 < page_bbox[0] - margin or x2 > page_bbox[2] + margin:
                print(f"    ❌ Block {block_idx} X 坐标超出页面: [{x1:.1f}, {x2:.1f}] vs page [{page_bbox[0]:.1f}, {page_bbox[2]:.1f}]")
                all_checks_passed = False

            if y1 < page_bbox[1] - margin or y2 > page_bbox[3] + margin:
                print(f"    ❌ Block {block_idx} Y 坐标超出页面: [{y1:.1f}, {y2:.1f}] vs page [{page_bbox[1]:.1f}, {page_bbox[3]:.1f}]")
                all_checks_passed = False

            # 检查 5: Block 的 top_k
            if hasattr(block, "top_k") and block.top_k:
                max_conf = max(block.top_k.values())
            else:
                max_conf = 0.0

            print(f"    ✅ Block {block_idx}: {block.block_type.name}, bbox=[{x1:.0f},{y1:.0f},{x2:.0f},{y2:.0f}], conf={max_conf:.2f}")

    if all_checks_passed:
        print(f"\n[Validator] ✅ All layout structure checks passed for {backend_name}")
    else:
        print(f"\n[Validator] ❌ Some layout structure checks failed for {backend_name}")

    return all_checks_passed


def test_backend(backend_name: str, pdf_path: str, config: dict):
    """测试单个 layout 后端"""
    print(f"\n{'=' * 60}")
    print(f"Testing backend: {backend_name}")
    print(f"{'=' * 60}")

    try:
        from aih_contexture.converters.pdf import PdfConverter
        from aih_contexture.scripts.common import load_models

        # 加载模型
        print("[Validator] Loading models...")
        artifacts = load_models()

        # 创建转换器
        print(f"[Validator] Creating converter with config: {config}")
        converter = PdfConverter(
            config=config,
            artifact_dict=artifacts,
        )

        # 构建文档
        print(f"[Validator] Building document from: {pdf_path}")
        document = converter.build_document(pdf_path)

        # 验证 layout structure
        passed = validate_layout_structure(document, backend_name)

        # 额外检查：LineBuilder 是否运行成功
        print(f"\n[Validator] Checking if LineBuilder completed successfully...")
        has_lines = False
        for page in document.pages:
            if hasattr(page, "children") and page.children:
                has_lines = True
                break

        if has_lines:
            print(f"[Validator] ✅ LineBuilder successfully generated line blocks")
        else:
            print(f"[Validator] ⚠️  No line blocks found (may be expected for some backends)")

        return passed

    except Exception as e:
        print(f"[Validator] ❌ Exception during testing {backend_name}: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主验证流程"""
    print("=" * 60)
    print("Marker Layout Backend Validator")
    print("=" * 60)

    # 获取测试 PDF
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
        if not os.path.exists(pdf_path):
            print(f"[Validator] ❌ PDF not found: {pdf_path}")
            return
    else:
        print("[Validator] No PDF provided, creating test PDF...")
        pdf_path = create_test_pdf()
        if not pdf_path:
            print("[Validator] ❌ Cannot create test PDF, exiting")
            return

    print(f"\n[Validator] Using PDF: {pdf_path}")

    # 测试配置
    results = {}

    # 测试 1: Surya Layout（默认）
    print("\n" + "=" * 60)
    print("Test 1: Surya Layout Backend")
    print("=" * 60)
    results["surya"] = test_backend(
        "surya",
        pdf_path,
        {"layout_backend": "surya"}
    )

    # 测试 2: VLM Layout（如果配置了 OpenAI）
    openai_base_url = os.environ.get("OPENAI_BASE_URL", "http://127.0.0.1:1234/v1")
    openai_model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    openai_api_key = os.environ.get("OPENAI_API_KEY", "lm-studio")

    print("\n" + "=" * 60)
    print("Test 2: VLM Layout Backend")
    print("=" * 60)
    print(f"[Validator] VLM Config: {openai_base_url} / {openai_model}")
    print("[Validator] Set OPENAI_BASE_URL, OPENAI_MODEL, OPENAI_API_KEY to test VLM")

    vlm_config = {
        "layout_backend": "vlm",
        "vlm_layout_prompt_template": "modern",
        "openai_base_url": openai_base_url,
        "openai_model": openai_model,
        "openai_api_key": openai_api_key,
    }

    try:
        results["vlm"] = test_backend("vlm", pdf_path, vlm_config)
    except Exception as e:
        print(f"[Validator] ⚠️  VLM backend test skipped: {e}")
        results["vlm"] = None

    # 测试 3: YOLO Layout（如果服务可用）
    yolo_base_url = os.environ.get("YOLO_BASE_URL", "http://localhost:11900")

    print("\n" + "=" * 60)
    print("Test 3: YOLO Layout Backend")
    print("=" * 60)
    print(f"[Validator] YOLO Config: {yolo_base_url}")
    print("[Validator] Set YOLO_BASE_URL to test YOLO (requires Docker service)")

    yolo_config = {
        "layout_backend": "yolo",
        "yolo_base_url": yolo_base_url,
        "yolo_model": "doclayout_yolo",
        "yolo_confidence_threshold": 0.25,
    }

    try:
        results["yolo"] = test_backend("yolo", pdf_path, yolo_config)
    except Exception as e:
        print(f"[Validator] ⚠️  YOLO backend test skipped: {e}")
        results["yolo"] = None

    # 汇总结果
    print("\n" + "=" * 60)
    print("Validation Summary")
    print("=" * 60)

    for backend, passed in results.items():
        if passed is None:
            status = "⊝ SKIPPED"
        elif passed:
            status = "✅ PASSED"
        else:
            status = "❌ FAILED"
        print(f"  {backend.ljust(10)}: {status}")

    all_passed = all(r for r in results.values() if r is not None)
    if all_passed:
        print("\n🎉 All tested backends passed validation!")
    else:
        print("\n⚠️  Some backends failed validation. Check logs above.")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
