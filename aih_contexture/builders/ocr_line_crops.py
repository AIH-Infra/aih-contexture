from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from PIL import Image

from aih_contexture.providers.pdf import PdfProvider
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup


DEFAULT_SKIP_OCR_BLOCKS = {
    BlockTypes.Equation,
    BlockTypes.Figure,
    BlockTypes.Picture,
    BlockTypes.Table,
    BlockTypes.Form,
    BlockTypes.TableOfContents,
}

DEFAULT_OCR_CROP_PADDING_PX = 8
DEFAULT_OCR_CROP_PADDING_FRAC = 0.12
DEFAULT_OCR_CROP_UPSCALE_MIN_HEIGHT = 32


@dataclass(frozen=True, slots=True)
class OcrLineCrop:
    page: PageGroup
    block_id: str
    line_id: str
    block_type: str
    original_bbox: tuple[int, int, int, int]
    padded_bbox: tuple[int, int, int, int]
    image: Image.Image


class OcrLineCropper:
    """Collect stable OCR line crops from Contexture line blocks."""

    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or {}
        self.padding_px = int(self.config.get("ocr_crop_padding_px", DEFAULT_OCR_CROP_PADDING_PX))
        self.padding_frac = float(self.config.get("ocr_crop_padding_frac", DEFAULT_OCR_CROP_PADDING_FRAC))
        self.min_width = int(self.config.get("ocr_crop_min_width", 20))
        self.min_height = int(self.config.get("ocr_crop_min_height", 8))
        self.min_area = int(self.config.get("ocr_crop_min_area", 100))
        self.preprocess = str(self.config.get("ocr_crop_preprocess") or self._legacy_preprocess()).lower()
        self.upscale_min_height = int(
            self.config.get("ocr_crop_upscale_min_height", DEFAULT_OCR_CROP_UPSCALE_MIN_HEIGHT)
        )

    def collect_page_crops(
        self,
        document: Document,
        page: PageGroup,
        provider: PdfProvider,
        *,
        skip_blocks: set[BlockTypes] | None = None,
    ) -> list[OcrLineCrop]:
        page_highres_image = page.get_image(highres=True) or page.get_image(highres=False)
        if page_highres_image is None:
            return []

        page_size = provider.get_page_bbox(page.page_id).size
        image_size = page_highres_image.size
        skip_blocks = skip_blocks or DEFAULT_SKIP_OCR_BLOCKS

        crops: list[OcrLineCrop] = []
        for block in page.structure_blocks(document):
            if block.block_type in skip_blocks:
                continue
            block_type_name = str(block.block_type.name) if hasattr(block.block_type, "name") else str(block.block_type)
            block.text_extraction_method = "surya"
            for line_block in block.contained_blocks(document, [BlockTypes.Line]):
                line_polygon = (
                    copy.deepcopy(line_block.polygon)
                    .rescale(page_size, image_size)
                    .fit_to_bounds((0, 0, *image_size))
                )
                bbox = _int_bbox(line_polygon.bbox)
                x0, y0, x1, y1 = bbox
                width = x1 - x0
                height = y1 - y0
                if width < self.min_width or height < self.min_height or width * height < self.min_area:
                    continue
                padded_bbox = _pad_bbox(
                    bbox,
                    image_size=image_size,
                    padding_px=self.padding_px,
                    padding_frac=self.padding_frac,
                )
                if padded_bbox[2] <= padded_bbox[0] or padded_bbox[3] <= padded_bbox[1]:
                    continue
                image = page_highres_image.crop(padded_bbox)
                image = self.preprocess_image(image)
                crops.append(
                    OcrLineCrop(
                        page=page,
                        block_id=block.id,
                        line_id=line_block.id,
                        block_type=block_type_name,
                        original_bbox=bbox,
                        padded_bbox=padded_bbox,
                        image=image,
                    )
                )
        crops.sort(key=lambda item: (item.padded_bbox[1], item.padded_bbox[0], item.padded_bbox[3], item.padded_bbox[2]))
        return crops

    def preprocess_image(self, image: Image.Image) -> Image.Image:
        processed = image
        if self.preprocess == "otsu":
            processed = _otsu_binarize(processed)
        elif self.preprocess == "adaptive":
            processed = _adaptive_binarize(processed)
        if self.upscale_min_height > 0 and processed.height < self.upscale_min_height and processed.height > 0:
            scale = self.upscale_min_height / processed.height
            new_size = (max(1, int(processed.width * scale)), self.upscale_min_height)
            processed = processed.resize(new_size, Image.Resampling.BICUBIC)
        return processed

    def _legacy_preprocess(self) -> str:
        if self.config.get("calamari_binarize_lines", False):
            return "otsu"
        if self.config.get("tesseract_preprocess"):
            return str(self.config["tesseract_preprocess"])
        return "otsu"


def _int_bbox(bbox: list[float]) -> tuple[int, int, int, int]:
    import math

    x0, y0, x1, y1 = bbox
    return math.floor(x0), math.floor(y0), math.ceil(x1), math.ceil(y1)


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


def _otsu_binarize(image: Image.Image) -> Image.Image:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return image

    array = np.array(image)
    if len(array.shape) == 3:
        gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    else:
        gray = array
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return Image.fromarray(binary, mode="L")


def _adaptive_binarize(image: Image.Image) -> Image.Image:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return image

    array = np.array(image)
    if len(array.shape) == 3:
        gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    else:
        gray = array
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 11)
    return Image.fromarray(binary, mode="L")
