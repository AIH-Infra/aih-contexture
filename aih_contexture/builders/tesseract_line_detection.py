from __future__ import annotations

import copy
import math
from typing import Iterable

from aih_contexture.builders.ocr_line_crops import (
    DEFAULT_OCR_CROP_PADDING_FRAC,
    DEFAULT_OCR_CROP_PADDING_PX,
    OcrLineCropper,
)
from aih_contexture.providers import ProviderOutput
from aih_contexture.providers.pdf import PdfProvider
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.schema.polygon import PolygonBox
from aih_contexture.schema.registry import get_block_class
from aih_contexture.services.ocr_tesseract import TesseractOcrService


DEFAULT_TESSERACT_LINE_SKIP_BLOCKS = {
    BlockTypes.Equation,
    BlockTypes.Figure,
    BlockTypes.Picture,
    BlockTypes.Table,
    BlockTypes.Form,
    BlockTypes.TableOfContents,
}


def page_has_line_blocks(document: Document, page: PageGroup) -> bool:
    return any(
        bool(block.contained_blocks(document, [BlockTypes.Line]))
        for block in page.structure_blocks(document)
    )


def ensure_tesseract_line_blocks(
    document: Document,
    page: PageGroup,
    provider: PdfProvider,
    service: TesseractOcrService,
    *,
    skip_blocks: Iterable[BlockTypes] | None = None,
    write_tesseract_text: bool = True,
) -> int:
    if page_has_line_blocks(document, page):
        return 0

    highres_image = page.get_image(highres=True) or page.get_image(highres=False)
    if highres_image is None:
        return 0

    page_size = provider.get_page_bbox(page.page_id).size
    image_size = highres_image.size
    skip = set(skip_blocks or DEFAULT_TESSERACT_LINE_SKIP_BLOCKS)
    outputs: list[ProviderOutput] = []
    line_preprocessor = OcrLineCropper(_line_preprocess_config(service.config))
    if str(service.config.get("tesseract_line_scope") or "page").strip().lower() == "page":
        page_crop = line_preprocessor.preprocess_image(highres_image)
        detection_image_size = page_crop.size
        try:
            detected_lines = service.recognize_hocr_lines(page_crop)
        except Exception:
            detected_lines = []
        if detected_lines:
            skip_bboxes = _skip_block_bboxes(document, page, page_size, image_size, skip)
            for detected in detected_lines:
                detected_bbox = _rescale_bbox(detected.bbox, detection_image_size, image_size)
                if _bbox_center_inside_any(detected_bbox, skip_bboxes):
                    continue
                global_bbox = _pad_bbox(
                    detected_bbox,
                    image_size=image_size,
                    padding_px=int(service.config.get("ocr_crop_padding_px", DEFAULT_OCR_CROP_PADDING_PX)),
                    padding_frac=float(service.config.get("ocr_crop_padding_frac", DEFAULT_OCR_CROP_PADDING_FRAC)),
                )
                line_polygon = PolygonBox.from_bbox(global_bbox, ensure_nonzero_area=True).rescale(
                    image_size,
                    page_size,
                )
                outputs.append(_provider_output_from_line(
                    page_id=page.page_id,
                    polygon=line_polygon,
                    text=detected.text if write_tesseract_text else "",
                    confidence=detected.confidence,
                ))
            if outputs:
                page.text_extraction_method = "surya"
                page.merge_blocks(outputs, text_extraction_method="surya")
                for block in page.structure_blocks(document):
                    block.set_internal_metadata("line_detection_backend", "tesseract_hocr")
                    if write_tesseract_text:
                        block.set_internal_metadata("ocr_backend", "tesseract")
                return len(outputs)

    for block in page.structure_blocks(document):
        if block.block_type in skip:
            continue
        block_image_polygon = (
            copy.deepcopy(block.polygon)
            .rescale(page_size, image_size)
            .fit_to_bounds((0, 0, *image_size))
        )
        block_bbox = _int_bbox(block_image_polygon.bbox)
        block_bbox = _pad_bbox(
            block_bbox,
            image_size=image_size,
            padding_px=int(service.config.get("ocr_crop_padding_px", DEFAULT_OCR_CROP_PADDING_PX)),
            padding_frac=float(service.config.get("ocr_crop_padding_frac", DEFAULT_OCR_CROP_PADDING_FRAC)),
        )
        if block_bbox[2] <= block_bbox[0] or block_bbox[3] <= block_bbox[1]:
            continue
        crop = line_preprocessor.preprocess_image(highres_image.crop(block_bbox))
        try:
            detected_lines = service.recognize_lines(crop)
        except Exception:
            continue
        for detected in detected_lines:
            global_bbox = _offset_bbox(detected.bbox, block_bbox[0], block_bbox[1])
            global_bbox = _pad_bbox(
                global_bbox,
                image_size=image_size,
                padding_px=int(service.config.get("ocr_crop_padding_px", DEFAULT_OCR_CROP_PADDING_PX)),
                padding_frac=float(service.config.get("ocr_crop_padding_frac", DEFAULT_OCR_CROP_PADDING_FRAC)),
            )
            line_polygon = PolygonBox.from_bbox(global_bbox, ensure_nonzero_area=True).rescale(
                image_size,
                page_size,
            )
            outputs.append(_provider_output_from_line(
                page_id=page.page_id,
                polygon=line_polygon,
                text=detected.text if write_tesseract_text else "",
                confidence=detected.confidence,
            ))

    if not outputs:
        return 0

    page.text_extraction_method = "surya"
    page.merge_blocks(outputs, text_extraction_method="surya")
    for block in page.structure_blocks(document):
        block.set_internal_metadata("line_detection_backend", "tesseract")
        if write_tesseract_text:
            block.set_internal_metadata("ocr_backend", "tesseract")
    return len(outputs)


def _skip_block_bboxes(
    document: Document,
    page: PageGroup,
    page_size: tuple[float, float],
    image_size: tuple[int, int],
    skip: set[BlockTypes],
) -> list[tuple[int, int, int, int]]:
    bboxes: list[tuple[int, int, int, int]] = []
    for block in page.structure_blocks(document):
        if block.block_type not in skip:
            continue
        block_image_polygon = (
            copy.deepcopy(block.polygon)
            .rescale(page_size, image_size)
            .fit_to_bounds((0, 0, *image_size))
        )
        bboxes.append(_int_bbox(block_image_polygon.bbox))
    return bboxes


def _bbox_center_inside_any(
    bbox: tuple[int, int, int, int],
    containers: list[tuple[int, int, int, int]],
) -> bool:
    if not containers:
        return False
    x0, y0, x1, y1 = bbox
    cx = (x0 + x1) / 2
    cy = (y0 + y1) / 2
    return any(sx0 <= cx <= sx1 and sy0 <= cy <= sy1 for sx0, sy0, sx1, sy1 in containers)


def _line_preprocess_config(config: dict) -> dict:
    preprocess = (
        config.get("tesseract_line_preprocess")
        or config.get("ocr_crop_preprocess")
        or "otsu"
    )
    return {
        "ocr_crop_preprocess": preprocess,
        "ocr_crop_upscale_min_height": int(config.get("tesseract_line_upscale_min_height") or 0),
    }


def _provider_output_from_line(
    *,
    page_id: int,
    polygon: PolygonBox,
    text: str,
    confidence: float | None,
) -> ProviderOutput:
    LineClass = get_block_class(BlockTypes.Line)
    SpanClass = get_block_class(BlockTypes.Span)
    line = LineClass(
        polygon=polygon,
        page_id=page_id,
        text_extraction_method="surya",
    )
    span = SpanClass(
        text=(text.strip() + " ") if text.strip() else "",
        formats=["plain"],
        page_id=page_id,
        polygon=polygon,
        minimum_position=0,
        maximum_position=0,
        font="Unknown",
        font_weight=0,
        font_size=0,
    )
    span.text_extraction_method = "surya"
    if confidence is not None:
        line.set_internal_metadata("tesseract_confidence", confidence)
        span.set_internal_metadata("tesseract_confidence", confidence)
    line.set_internal_metadata("line_detection_backend", "tesseract")
    span.set_internal_metadata("line_detection_backend", "tesseract")
    if text.strip():
        line.set_internal_metadata("ocr_backend", "tesseract")
        span.set_internal_metadata("ocr_backend", "tesseract")
    return ProviderOutput(line=line, spans=[span], chars=[])


def _int_bbox(bbox: list[float]) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox
    return math.floor(x0), math.floor(y0), math.ceil(x1), math.ceil(y1)


def _offset_bbox(
    bbox: tuple[int, int, int, int],
    offset_x: int,
    offset_y: int,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox
    return x0 + offset_x, y0 + offset_y, x1 + offset_x, y1 + offset_y


def _rescale_bbox(
    bbox: tuple[int, int, int, int],
    from_size: tuple[int, int],
    to_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    if from_size == to_size:
        return bbox
    from_width, from_height = from_size
    to_width, to_height = to_size
    if from_width <= 0 or from_height <= 0:
        return bbox
    scale_x = to_width / from_width
    scale_y = to_height / from_height
    x0, y0, x1, y1 = bbox
    return (
        int(round(x0 * scale_x)),
        int(round(y0 * scale_y)),
        int(round(x1 * scale_x)),
        int(round(y1 * scale_y)),
    )


def _pad_bbox(
    bbox: tuple[int, int, int, int],
    *,
    image_size: tuple[int, int],
    padding_px: int,
    padding_frac: float,
) -> tuple[int, int, int, int]:
    x0, y0, x1, y1 = bbox
    width = max(0, x1 - x0)
    height = max(0, y1 - y0)
    pad_x = int(round(max(padding_px, width * padding_frac)))
    pad_y = int(round(max(padding_px, height * padding_frac)))
    image_width, image_height = image_size
    return (
        max(0, x0 - pad_x),
        max(0, y0 - pad_y),
        min(image_width, x1 + pad_x),
        min(image_height, y1 + pad_y),
    )
