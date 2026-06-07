from surya.layout.schema import LayoutResult

from aih_contexture.builders.document import DocumentBuilder
from aih_contexture.builders.layout import LayoutBuilder
from aih_contexture.builders.line import LineBuilder


def test_blank_page(config, doc_provider, layout_model, ocr_error_model, detection_model):
    layout_builder = LayoutBuilder(layout_model, config)
    line_builder = LineBuilder(detection_model, ocr_error_model)
    builder = DocumentBuilder(config)
    document = builder.build_document(doc_provider)

    layout_results = [LayoutResult(
        bboxes=[],
        image_bbox=p.polygon.bbox,
    ) for p in document.pages]
    provider_lines = {p.page_id: [] for p in document.pages}
    ocr_lines = {p.page_id: [] for p in document.pages}

    layout_builder.add_blocks_to_pages(document.pages, layout_results)
    line_builder.merge_blocks(document, provider_lines, ocr_lines)

    assert all([isinstance(p.children, list) for p in document.pages])
    assert all([isinstance(p.structure, list) for p in document.pages])