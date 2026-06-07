import json

from aih_contexture.evaluation.layout_middle import (
    evaluate_middle_layout,
    evaluate_middle_layout_files,
    evaluate_middle_layout_manifest,
)
from aih_contexture.middle.schema import MiddleBlock, MiddleDocument, MiddlePage, MiddleProvenance, MiddleSpan


def _sample_middle():
    return MiddleDocument(
        source_name="sample.pdf",
        backends={"layout": "external_layout_sidecar", "ocr": "none"},
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
                        spans=[
                            MiddleSpan(
                                text="sample",
                                bbox=[10, 20, 50, 40],
                                provenance=[MiddleProvenance(backend="native_pdf", stage="text")],
                            ),
                            MiddleSpan(text="untraced"),
                        ],
                        provenance=[MiddleProvenance(backend="surya", stage="layout")],
                    ),
                    MiddleBlock(
                        id="p0-b1",
                        type="Footnote",
                        page_index=0,
                        order=1,
                        bbox=[10, 160, 90, 190],
                        provenance=[MiddleProvenance(backend="surya", stage="layout")],
                    ),
                ],
            )
        ],
    ).to_dict()


def test_evaluate_middle_layout_reports_required_type_coverage():
    result = evaluate_middle_layout(
        _sample_middle(),
        required_block_types=["Text", "Footnote"],
    )

    assert result["ok"] is True
    assert result["metrics"]["block_count"] == 2
    assert result["metrics"]["block_types"] == {"Footnote": 1, "Text": 1}
    assert result["metrics"]["span_count"] == 2
    assert result["metrics"]["blocks_with_spans"] == 1
    assert result["metrics"]["spans_missing_bbox"] == 1
    assert result["metrics"]["spans_missing_provenance"] == 1
    assert result["metrics"]["span_provenance_completeness"] == 0.5
    assert result["metrics"]["missing_required_block_types"] == []


def test_evaluate_middle_layout_fails_when_required_type_is_missing():
    result = evaluate_middle_layout(
        _sample_middle(),
        required_block_types=["Table"],
    )

    assert result["ok"] is False
    assert result["validation_ok"] is True
    assert result["metrics"]["missing_required_block_types"] == ["Table"]


def test_evaluate_middle_layout_flags_small_empty_complex_regions():
    payload = MiddleDocument(
        source_name="sample.pdf",
        pages=[
            MiddlePage(
                index=0,
                width=100,
                height=100,
                blocks=[
                    MiddleBlock(
                        id="p0-b0",
                        type="ComplexRegion",
                        page_index=0,
                        order=0,
                        bbox=[0, 0, 5, 5],
                        provenance=[MiddleProvenance(backend="paddle_pp_doclayout_v3", stage="layout")],
                    )
                ],
            )
        ],
    ).to_dict()

    result = evaluate_middle_layout(payload)

    assert result["ok"] is True
    assert result["metrics"]["empty_complex_regions"] == 1
    assert result["metrics"]["small_empty_complex_regions"] == 1


def test_evaluate_middle_layout_files_aggregates_cases(tmp_path):
    path = tmp_path / "sample_middle.json"
    path.write_text(json.dumps(_sample_middle()), encoding="utf-8")

    payload = evaluate_middle_layout_files([path], required_block_types=["Text"])

    assert payload["ok"] is True
    assert payload["case_count"] == 1
    assert payload["results"][0]["source_path"] == str(path)


def test_evaluate_middle_layout_manifest_supports_case_metadata(tmp_path):
    path = tmp_path / "sample_middle.json"
    path.write_text(json.dumps(_sample_middle()), encoding="utf-8")
    manifest = {
        "name": "smoke-layout",
        "version": 1,
        "min_blocks": 1,
        "cases": [
            {
                "id": "modern-footnote",
                "path": "sample_middle.json",
                "backend": "surya",
                "document_type": "modern_pdf",
                "source_pdf": "sample.pdf",
                "page_range": [0],
                "required_block_types": ["Text", "Footnote"],
            }
        ],
    }

    payload = evaluate_middle_layout_manifest(manifest, base_dir=tmp_path)

    assert payload["ok"] is True
    assert payload["manifest"] == {"name": "smoke-layout", "version": 1}
    assert payload["results"][0]["case"]["id"] == "modern-footnote"
    assert payload["results"][0]["case"]["backend"] == "surya"
    assert payload["results"][0]["case"]["source_pdf"] == "sample.pdf"
    assert payload["results"][0]["case"]["page_range"] == [0]
