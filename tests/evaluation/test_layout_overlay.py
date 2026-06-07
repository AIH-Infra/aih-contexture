import json

from PIL import Image

from aih_contexture.evaluation.layout_overlay import (
    render_middle_layout_overlay,
    render_middle_review_crops,
    render_middle_span_overlay,
)
from aih_contexture.middle.schema import MiddleBlock, MiddleDocument, MiddlePage, MiddleProvenance, MiddleSpan


def _sample_middle():
    return MiddleDocument(
        source_name="sample.pdf",
        backends={"layout": "paddle_pp_doclayout_v3", "ocr": "none"},
        pages=[
            MiddlePage(
                index=0,
                width=100,
                height=200,
                blocks=[
                    MiddleBlock(
                        id="p0-b0",
                        type="Text",
                        page_index=0,
                        order=0,
                        bbox=[10, 20, 90, 80],
                        confidence=0.9,
                        spans=[
                            MiddleSpan(
                                text="hello",
                                bbox=[12, 24, 42, 36],
                                provenance=[MiddleProvenance(backend="surya", stage="span")],
                            )
                        ],
                        provenance=[MiddleProvenance(backend="paddle", stage="layout")],
                    ),
                    MiddleBlock(
                        id="p0-b1",
                        type="Footnote",
                        page_index=0,
                        order=1,
                        bbox=[10, 160, 90, 190],
                        provenance=[MiddleProvenance(backend="paddle", stage="layout")],
                    ),
                ],
            )
        ],
    ).to_dict()


def test_render_middle_layout_overlay_writes_png_and_pdf(tmp_path):
    report = render_middle_layout_overlay(
        _sample_middle(),
        output_dir=tmp_path / "overlay",
        output_pdf=tmp_path / "overlay.pdf",
        dpi=72,
    )

    assert report["ok"] is True
    assert report["page_count"] == 1
    assert report["pdf"] == str(tmp_path / "overlay.pdf")
    assert (tmp_path / "overlay.pdf").exists()
    image_path = tmp_path / "overlay" / "page_0000_layout_overlay.png"
    assert report["images"] == [str(image_path)]
    assert image_path.exists()

    image = Image.open(image_path)
    assert image.size == (100, 200)


def test_render_middle_layout_overlay_skips_blocks_without_bbox(tmp_path):
    middle = _sample_middle()
    middle["pages"][0]["blocks"][0]["bbox"] = None

    report = render_middle_layout_overlay(middle, output_dir=tmp_path / "overlay", dpi=72)

    assert report["ok"] is True
    image_path = tmp_path / "overlay" / "page_0000_layout_overlay.png"
    assert json.loads(json.dumps(report))["images"] == [str(image_path)]


def test_render_middle_span_overlay_writes_span_pdf(tmp_path):
    report = render_middle_span_overlay(
        _sample_middle(),
        output_dir=tmp_path / "span",
        output_pdf=tmp_path / "span.pdf",
        dpi=72,
    )

    assert report["ok"] is True
    assert report["span_count"] == 1
    assert (tmp_path / "span" / "page_0000_span_overlay.png").exists()
    assert (tmp_path / "span.pdf").exists()


def test_render_middle_review_crops_writes_small_empty_complex_manifest(tmp_path):
    middle = _sample_middle()
    middle["pages"][0]["blocks"].append(
        {
            "id": "p0-b2",
            "type": "ComplexRegion",
            "page_index": 0,
            "order": 2,
            "text": "",
            "anchor_start": 0,
            "anchor_end": 1,
            "bbox": [5, 5, 12, 12],
            "polygon": None,
            "confidence": None,
            "spans": [],
            "children": [],
            "attrs": {},
            "provenance": [{"backend": "paddle", "stage": "layout"}],
        }
    )

    report = render_middle_review_crops(middle, output_dir=tmp_path / "review", dpi=72)

    assert report["ok"] is True
    assert report["crop_count"] == 1
    assert report["crops"][0]["block_id"] == "p0-b2"
    assert (tmp_path / "review" / "review_crops.json").exists()
    assert (tmp_path / "review" / "page_0000_block_0002_ComplexRegion_review.png").exists()
