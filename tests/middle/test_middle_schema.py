from aih_contexture.middle import (
    CANONICAL_BLOCK_TYPES,
    MiddleBlock,
    MiddleDocument,
    MiddlePage,
    MiddleProvenance,
    MiddleSpan,
)


def test_middle_document_serializes_page_interval_anchors():
    block = MiddleBlock(
        id="p0-b0",
        type="Footnote",
        page_index=0,
        order=0,
        text="note",
        provenance=[MiddleProvenance(backend="surya", stage="layout", raw_label="Footnote")],
    )
    page = MiddlePage(index=0, width=100, height=200, printed_page="i", blocks=[block])
    document = MiddleDocument(source_name="sample.pdf", pages=[page])

    data = document.to_dict()

    assert data["schema_version"] == "contexture-middle-json/0.1"
    assert data["page_count"] == 1
    assert document.page_count == 1
    assert data["pages"][0]["anchor_start"] == 0
    assert data["pages"][0]["anchor_end"] == 1
    assert data["pages"][0]["blocks"][0]["anchor_start"] == 0
    assert data["pages"][0]["blocks"][0]["anchor_end"] == 1
    assert data["pages"][0]["blocks"][0]["provenance"][0]["raw_label"] == "Footnote"


def test_middle_schema_covers_humanities_canonical_blocks():
    required = {
        "PageHeader",
        "PageFooter",
        "Footnote",
        "MarginalNote",
        "InlineAnnotation",
        "Reference",
        "ImageDescription",
    }

    assert required.issubset(set(CANONICAL_BLOCK_TYPES))


def test_middle_span_keeps_verifiable_geometry_and_backend_trace():
    span = MiddleSpan(
        text="abc",
        bbox=[0, 1, 2, 3],
        confidence=0.9,
        provenance=[MiddleProvenance(backend="paddle_ocr_v5", stage="ocr")],
    )

    assert span.bbox == [0, 1, 2, 3]
    assert span.provenance[0].backend == "paddle_ocr_v5"
