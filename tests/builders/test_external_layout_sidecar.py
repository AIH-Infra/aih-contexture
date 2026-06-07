import json

from PIL import Image

from aih_contexture.builders.external_layout_sidecar import (
    ExternalLayoutSidecarBuilder,
    _layout_label,
)
from aih_contexture.builders.mineru_layout import MineruLayoutBuilder
from aih_contexture.builders.paddle_layout import PaddleLayoutDetectionBuilder
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.schema.polygon import PolygonBox


def test_external_layout_sidecar_maps_middle_labels_to_layout_labels(tmp_path):
    sidecar_path = tmp_path / "middle.json"
    sidecar_path.write_text(
        json.dumps(
            {
                "schema_version": "contexture-middle-json/0.1",
                "pages": [
                    {
                        "index": 0,
                        "width": 100,
                        "height": 200,
                        "blocks": [
                            {
                                "id": "p0-b0",
                                "type": "MarginalNote",
                                "page_index": 0,
                                "order": 0,
                                "bbox": [5, 10, 20, 50],
                                "confidence": 0.8,
                            },
                            {
                                "id": "p0-b1",
                                "type": "ImageDescription",
                                "page_index": 0,
                                "order": 1,
                                "bbox": [10, 60, 90, 80],
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    page = PageGroup(
        polygon=PolygonBox.from_bbox([0, 0, 100, 200]),
        page_id=0,
        children=[],
        structure=[],
    )
    builder = ExternalLayoutSidecarBuilder(
        config={"external_layout_json": str(sidecar_path)}
    )

    layout_result = builder._layout_results_for_pages([page], builder._load_pages())[0]

    assert [bbox.label for bbox in layout_result.bboxes] == ["MarginalAnnotation", "Caption"]
    assert layout_result.bboxes[0].top_k == {"MarginalAnnotation": 0.8}


def test_external_layout_sidecar_adds_blocks_to_document(tmp_path):
    sidecar_path = tmp_path / "layout.json"
    sidecar_path.write_text(
        json.dumps(
            {
                "pdf_info": [
                    {
                        "page_idx": 0,
                        "page_size": [100, 200],
                        "layout_bboxes": [
                            {"layout_label": "title", "layout_bbox": [5, 10, 80, 30]},
                            {"layout_label": "page_footnote", "layout_bbox": [5, 150, 80, 190]},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    page = PageGroup(
        polygon=PolygonBox.from_bbox([0, 0, 100, 200]),
        page_id=0,
        children=[],
        structure=[],
    )
    document = Document(filepath="sample.pdf", pages=[page])
    builder = ExternalLayoutSidecarBuilder(
        config={
            "external_layout_json": str(sidecar_path),
            "external_layout_backend_name": "mineru_pp_doclayout_v2",
        }
    )

    builder(document, provider=None)

    assert [document.get_block(block_id).block_type for block_id in page.structure] == [
        BlockTypes.SectionHeader,
        BlockTypes.Footnote,
    ]


def test_external_layout_sidecar_rejects_missing_pages_by_default(tmp_path):
    sidecar_path = tmp_path / "middle.json"
    sidecar_path.write_text(
        json.dumps({"schema_version": "contexture-middle-json/0.1", "pages": []}),
        encoding="utf-8",
    )
    page = PageGroup(
        polygon=PolygonBox.from_bbox([0, 0, 100, 200]),
        page_id=0,
        children=[],
        structure=[],
    )
    builder = ExternalLayoutSidecarBuilder(
        config={"external_layout_json": str(sidecar_path)}
    )

    try:
        builder._layout_results_for_pages([page], builder._load_pages())
    except ValueError as exc:
        assert "does not contain" in str(exc)
    else:
        raise AssertionError("missing sidecar page should be rejected")


def test_external_layout_sidecar_middle_to_layout_fallbacks_are_explicit():
    assert _layout_label("PageNumber") == "PageFooter"
    assert _layout_label("MarginalNote") == "MarginalAnnotation"
    assert _layout_label("UnknownHumanitiesBlock") == "ComplexRegion"


def test_mineru_layout_builder_reuses_sidecar_mapping(tmp_path):
    middle_path = tmp_path / "sample_middle.json"
    middle_path.write_text(
        json.dumps(
            {
                "pdf_info": [
                    {
                        "page_idx": 0,
                        "page_size": [100, 200],
                        "para_blocks": [
                            {"type": "title", "bbox": [5, 10, 80, 30]},
                            {"type": "page_footnote", "bbox": [5, 150, 80, 190]},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    class FakeRuntime:
        def run(self, input_path):
            class Result:
                middle_json_path = middle_path

            return Result()

    class FakeProvider:
        filepath = "sample.pdf"

    page = PageGroup(
        polygon=PolygonBox.from_bbox([0, 0, 100, 200]),
        page_id=0,
        children=[],
        structure=[],
    )
    document = Document(filepath="sample.pdf", pages=[page])
    builder = MineruLayoutBuilder(config={}, runtime=FakeRuntime())

    builder(document, FakeProvider())

    assert [document.get_block(block_id).block_type for block_id in page.structure] == [
        BlockTypes.SectionHeader,
        BlockTypes.Footnote,
    ]


def test_paddle_layout_builder_reuses_sidecar_mapping():
    class FakeRuntime:
        def run(self, image_paths, *, page_sizes=None):
            assert page_sizes == [(100, 200)]
            return [
                {
                    "res": {
                        "page_index": 0,
                        "page_size": [100, 200],
                        "boxes": [
                            {
                                "label": "paragraph_title",
                                "score": 0.9,
                                "coordinate": [5, 10, 80, 30],
                            },
                            {
                                "label": "figure_title",
                                "score": 0.8,
                                "coordinate": [5, 150, 80, 190],
                            },
                        ],
                    }
                }
            ]

    page = PageGroup(
        polygon=PolygonBox.from_bbox([0, 0, 100, 200]),
        page_id=0,
        children=[],
        structure=[],
        lowres_image=Image.new("RGB", (100, 200), "white"),
    )
    document = Document(filepath="sample.pdf", pages=[page])
    builder = PaddleLayoutDetectionBuilder(config={}, runtime=FakeRuntime())

    builder(document, provider=None)

    assert [document.get_block(block_id).block_type for block_id in page.structure] == [
        BlockTypes.SectionHeader,
        BlockTypes.Caption,
    ]
