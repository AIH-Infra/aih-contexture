"""
Calamari OCR Builder - Line-level OCR using Calamari service

Key fix: 按页发送，不按固定 batch_size 拆分，避免跨批次顺序问题
"""

import copy
from typing import Annotated, List, Optional, Tuple, Callable

from PIL import Image

from aih_contexture.builders import BaseBuilder
from aih_contexture.builders.ocr import OcrBuilder
from aih_contexture.providers.pdf import PdfProvider
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.schema.registry import get_block_class
from aih_contexture.services.ocr_calamari import CalamariOcrService
from aih_contexture.logger import get_logger

logger = get_logger()


class CalamariOcrBuilder(BaseBuilder):
    """
    Calamari OCR Builder:
    - 按页发送所有行（不按固定 batch_size 拆分）
    - 保证页内行顺序与 Marker 版面分析结果一致
    - 支持 sequential 模式作为降级方案
    """

    min_line_area: Annotated[int, "Minimum line area (px²) to OCR."] = 100
    min_line_width: Annotated[int, "Minimum line width (px) to OCR."] = 20
    min_line_height: Annotated[int, "Minimum line height (px) to OCR."] = 8

    skip_ocr_blocks: Annotated[List[BlockTypes], "Block types to skip OCR."] = [
        BlockTypes.Equation,
        BlockTypes.Figure,
        BlockTypes.Picture,
        BlockTypes.Table,
        BlockTypes.Form,
        BlockTypes.TableOfContents,
    ]

    line_ordering: Annotated[str, "Line ordering within block: 'y_then_x' or 'none'."] = "y_then_x"
    debug_mapping: Annotated[bool, "Output line mapping for debugging."] = False

    progress_callback: Optional[Callable[[int, int, str], None]] = None

    def __init__(self, calamari_service: CalamariOcrService, config=None):
        super().__init__(config)
        self.config = config or {}
        
        if calamari_service is None:
            raise ValueError("CalamariOcrBuilder requires CalamariService.")
        
        self.calamari_service = calamari_service
        self._ocr_helper = OcrBuilder(recognition_model=None, config=self.config)
        
        if isinstance(config, dict):
            self.debug_mapping = bool(config.get("calamari_debug_mapping", True))
            self.line_ordering = config.get("calamari_line_ordering", self.line_ordering)

    def __call__(self, document: Document, provider: PdfProvider):
        """Main entry point: OCR all pages that need it."""

        pages_to_ocr = [p for p in document.pages if p.text_extraction_method == "surya"]

        if not pages_to_ocr:
            logger.info("[CalamariOcrBuilder] No pages need OCR")
            return

        total_pages = len(pages_to_ocr)
        chunk_size = self.config.get("pages_per_batch", 1)

        # 🔍 调试日志
        logger.info(f"[CalamariOcrBuilder] 🔍 DEBUG: pages_per_batch from config = {chunk_size}")
        logger.info(f"[CalamariOcrBuilder] 🔍 DEBUG: config keys = {list(self.config.keys())[:20]}")

        if chunk_size > 1:
            # 多页批处理模式
            mode = "sequential" if self.calamari_service.calamari_sequential_mode else "batch"
            logger.info(
                f"[CalamariOcrBuilder] Multi-page mode: {total_pages} pages, "
                f"chunk_size={chunk_size}, mode={mode}"
            )
            self._ocr_multi_page_batch(document, pages_to_ocr, provider)
        else:
            # 单页模式（保持原有逻辑）
            mode = "sequential" if self.calamari_service.calamari_sequential_mode else "batch (per-page)"
            logger.info(
                f"[CalamariOcrBuilder] Single-page mode: {total_pages} pages, mode={mode}"
            )

            for page_idx, page in enumerate(pages_to_ocr):
                if self.progress_callback:
                    self.progress_callback(
                        page_idx + 1, total_pages, f"Calamari OCR page {page.page_id}"
                    )

                try:
                    self._ocr_single_page(document, page, provider)
                except Exception as e:
                    logger.error(f"[CalamariOcrBuilder] Error on page {page.page_id}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue

            logger.info("[CalamariOcrBuilder] ✅ All pages processed successfully")

    def _line_sort_key_within_block(self, bbox: Tuple[int, int, int, int]) -> Tuple[int, int]:
        """Sort key for lines within a single block (by y then x)."""
        x0, y0, x1, y1 = bbox
        return (int(y0), int(x0))

    def _binarize_image(self, pil_image: Image.Image) -> Image.Image:
        """对PIL图像进行Otsu二值化处理，失败时返回原图"""
        try:
            import cv2
            import numpy as np
        except ImportError:
            return pil_image

        try:
            img_array = np.array(pil_image)
            if len(img_array.shape) == 3:
                gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
            else:
                gray = img_array
            _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
            return Image.fromarray(binary, mode='L')
        except Exception as e:
            logger.warning(f"[CalamariOcrBuilder] Binarization failed: {e}")
            return pil_image

    def _ocr_single_page(
        self,
        document: Document,
        page: PageGroup,
        provider: PdfProvider,
    ):
        """OCR all lines on a single page - 单栏优化：全页稳定排序 + 页底(脚注)后置"""

        page_highres_image = page.get_image(highres=True)
        if page_highres_image is None:
            logger.warning(f"[CalamariOcrBuilder] No highres image for page {page.page_id}")
            return

        page_size = provider.get_page_bbox(page.page_id).size
        image_size = page_highres_image.size
        page_h = float(image_size[1])

        # 收集全页 line items: (line_id, block_type, bbox, crop_img)
        all_line_items: List[Tuple[str, str, Tuple[int, int, int, int], Image.Image]] = []
        block_count = 0

        for block in page.structure_blocks(document):
            if block.block_type in self.skip_ocr_blocks:
                continue

            block.text_extraction_method = "surya"
            block_type_name = str(block.block_type.name) if hasattr(block.block_type, "name") else str(block.block_type)
            block_count += 1

            block_lines = block.contained_blocks(document, [BlockTypes.Line])
            for line_block in block_lines:
                line_polygon_rescaled = (
                    copy.deepcopy(line_block.polygon)
                    .rescale(page_size, image_size)
                    .fit_to_bounds((0, 0, *image_size))
                )

                bbox = line_polygon_rescaled.bbox
                x0, y0, x1, y1 = bbox
                w = x1 - x0
                h = y1 - y0

                if w < self.min_line_width or h < self.min_line_height:
                    continue
                if (w * h) < self.min_line_area:
                    continue

                crop_bbox = (int(x0), int(y0), int(x1), int(y1))
                if crop_bbox[2] <= crop_bbox[0] or crop_bbox[3] <= crop_bbox[1]:
                    continue

                try:
                    crop_img = page_highres_image.crop(crop_bbox)
                    all_line_items.append((line_block.id, block_type_name, crop_bbox, crop_img))
                except Exception as e:
                    logger.warning(f"[CalamariOcrBuilder] Failed to crop line {line_block.id}: {e}")
                    continue

        if not all_line_items:
            logger.info(f"[CalamariOcrBuilder] No lines to OCR on page {page.page_id}")
            return

        # ---------- 关键：全页排序（单栏） ----------
        # 启发式：把页底区域（疑似脚注/出处/页码）后置，避免混入正文
        FOOTNOTE_Y_FRAC = float(self.config.get("calamari_footnote_y_frac", 0.83))  # 默认最后 17% 视为“页底区”
        y_threshold = page_h * FOOTNOTE_Y_FRAC

        def is_bottom_region(item: Tuple[str, str, Tuple[int, int, int, int], Image.Image]) -> bool:
            _, _, (x0, y0, x1, y1), _ = item
            y_center = (y0 + y1) * 0.5
            return y_center >= y_threshold

        def sort_key(item: Tuple[str, str, Tuple[int, int, int, int], Image.Image]):
            _, _, (x0, y0, x1, y1), _ = item
            # 单栏：以 y0 为主，x0 为辅
            return (int(y0), int(x0), int(y1), int(x1))

        top_items = [it for it in all_line_items if not is_bottom_region(it)]
        bottom_items = [it for it in all_line_items if is_bottom_region(it)]

        top_items.sort(key=sort_key)
        bottom_items.sort(key=sort_key)

        ordered_items = top_items + bottom_items
        # -------------------------------------------

        sorted_line_ids = [item[0] for item in ordered_items]
        sorted_crops = [item[3] for item in ordered_items]

        # 二值化处理
        if self.config.get("calamari_binarize_lines", True):
            logger.info(f"[CalamariOcrBuilder] Binarizing {len(sorted_crops)} line images")
            sorted_crops = [self._binarize_image(img) for img in sorted_crops]

        logger.info(
            f"[CalamariOcrBuilder] Sending {len(sorted_crops)} lines to Calamari "
            f"(page {page.page_id}, {block_count} blocks; bottom_region={len(bottom_items)})"
        )

        texts = self.calamari_service.ocr_page(sorted_crops)  # 整页一批发送 [7]
        logger.info(f"[CalamariOcrBuilder] Received {len(texts)} results from Calamari")

        if len(texts) != len(sorted_line_ids):
            logger.error(
                f"[CalamariOcrBuilder] Length mismatch! Sent {len(sorted_line_ids)}, got {len(texts)}. Padding/truncating."
            )
            if len(texts) < len(sorted_line_ids):
                texts.extend([""] * (len(sorted_line_ids) - len(texts)))
            else:
                texts = texts[: len(sorted_line_ids)]

        SpanClass = get_block_class(BlockTypes.Span)
        success_count = 0
        empty_count = 0
        error_count = 0

        for line_id, text in zip(sorted_line_ids, texts):
            if not text or not text.strip():
                empty_count += 1
                continue

            line_block = page.get_block(line_id)
            if line_block is None:
                logger.warning(f"[CalamariOcrBuilder] Line block not found: {line_id}")
                error_count += 1
                continue

            new_span = SpanClass(
                text=text.strip() + " ",
                formats=["plain"],
                page_id=page.page_id,
                polygon=line_block.polygon,
                minimum_position=0,
                maximum_position=0,
                font="Unknown",
                font_weight=0,
                font_size=0,
            )

            try:
                self._ocr_helper.replace_line_spans(document, page, line_block, [new_span])  # 写回逻辑沿用 [1][5]
                success_count += 1
            except Exception as e:
                logger.warning(f"[CalamariOcrBuilder] replace_line_spans failed for {line_id}: {e}")
                error_count += 1
                try:
                    self._fallback_replace_spans(document, page, line_block, new_span)
                    success_count += 1
                    error_count -= 1
                except Exception as e2:
                    logger.warning(f"[CalamariOcrBuilder] Fallback also failed: {e2}")

            try:
                line_block.set_internal_metadata("ocr_backend", "calamari")
            except Exception:
                pass

        logger.info(
            f"[CalamariOcrBuilder] Page {page.page_id} complete: written={success_count}, empty={empty_count}, errors={error_count}"
        )

    def _fallback_replace_spans(
        self,
        document: Document,
        page: PageGroup,
        line_block,
        new_span,
    ):
        """Fallback: clear old spans and add new one directly."""
        try:
            old_spans = line_block.contained_blocks(document, [BlockTypes.Span])
            for old_span in old_spans:
                old_span.removed = True
        except Exception:
            pass
        
        line_block.structure = []
        page.add_full_block(new_span)
        line_block.structure = [new_span.id]
    def _ocr_multi_page_batch(self, document, pages, provider):
        """多页批处理：N页的所有行一次性发送"""
        chunk_size = self.config.get("pages_per_batch", 1)
        total_pages = len(pages)
        global_line_index = 0

        for chunk_start in range(0, total_pages, chunk_size):
            chunk_pages = pages[chunk_start : chunk_start + chunk_size]

            if self.progress_callback:
                self.progress_callback(
                    chunk_start + len(chunk_pages), total_pages,
                    f"Calamari OCR pages {chunk_start+1}-{chunk_start+len(chunk_pages)}"
                )

            # 收集所有行
            all_items = []  # [(page, line_id, crop_img)]
            for page in chunk_pages:
                page_lines = self._collect_sorted_page_lines(document, page, provider)
                all_items.extend([(page, line_id, img) for line_id, img in page_lines])

            if not all_items:
                continue

            logger.info(
                f"[CalamariOcrBuilder] Processing chunk: {len(chunk_pages)} pages, "
                f"{len(all_items)} lines, global_start_index={global_line_index}"
            )

            # OCR
            images = [item[2] for item in all_items]
            texts = self.calamari_service.ocr_page(images, global_start_index=global_line_index)

            # 写回
            self._write_batch_results(document, all_items, texts)

            global_line_index += len(all_items)

        logger.info("[CalamariOcrBuilder] ✅ Multi-page batch processing complete")

    def _collect_sorted_page_lines(self, document, page, provider):
        """收集并排序单页的所有行，返回 [(line_id, crop_img)]"""
        page_highres_image = page.get_image(highres=True)
        if page_highres_image is None:
            logger.warning(f"[CalamariOcrBuilder] No highres image for page {page.page_id}")
            return []

        page_size = provider.get_page_bbox(page.page_id).size
        image_size = page_highres_image.size
        page_h = float(image_size[1])

        # 收集全页 line items
        all_line_items = []  # [(line_id, block_type, bbox, crop_img)]

        for block in page.structure_blocks(document):
            if block.block_type in self.skip_ocr_blocks:
                continue

            block.text_extraction_method = "surya"
            block_lines = block.contained_blocks(document, [BlockTypes.Line])

            for line_block in block_lines:
                line_polygon_rescaled = (
                    copy.deepcopy(line_block.polygon)
                    .rescale(page_size, image_size)
                    .fit_to_bounds((0, 0, *image_size))
                )

                bbox = line_polygon_rescaled.bbox
                x0, y0, x1, y1 = bbox
                w = x1 - x0
                h = y1 - y0

                if w < self.min_line_width or h < self.min_line_height:
                    continue
                if (w * h) < self.min_line_area:
                    continue

                crop_bbox = (int(x0), int(y0), int(x1), int(y1))
                if crop_bbox[2] <= crop_bbox[0] or crop_bbox[3] <= crop_bbox[1]:
                    continue

                try:
                    crop_img = page_highres_image.crop(crop_bbox)
                    all_line_items.append((line_block.id, str(block.block_type.name), crop_bbox, crop_img))
                except Exception as e:
                    logger.warning(f"[CalamariOcrBuilder] Failed to crop line {line_block.id}: {e}")
                    continue

        if not all_line_items:
            return []

        # 排序：脚注后置
        FOOTNOTE_Y_FRAC = float(self.config.get("calamari_footnote_y_frac", 0.83))
        y_threshold = page_h * FOOTNOTE_Y_FRAC

        def is_bottom_region(item):
            _, _, (x0, y0, x1, y1), _ = item
            y_center = (y0 + y1) * 0.5
            return y_center >= y_threshold

        def sort_key(item):
            _, _, (x0, y0, x1, y1), _ = item
            return (int(y0), int(x0), int(y1), int(x1))

        top_items = [it for it in all_line_items if not is_bottom_region(it)]
        bottom_items = [it for it in all_line_items if is_bottom_region(it)]

        top_items.sort(key=sort_key)
        bottom_items.sort(key=sort_key)

        ordered_items = top_items + bottom_items

        # 返回 (line_id, crop_img)
        result = [(item[0], item[3]) for item in ordered_items]

        # 二值化处理
        if self.config.get("calamari_binarize_lines", True):
            result = [(line_id, self._binarize_image(img)) for line_id, img in result]

        return result

    def _write_batch_results(self, document, all_items, texts):
        """批量写回结果"""
        SpanClass = get_block_class(BlockTypes.Span)
        success_count = 0
        empty_count = 0
        error_count = 0

        for (page, line_id, _), text in zip(all_items, texts):
            if not text or not text.strip():
                empty_count += 1
                continue

            line_block = page.get_block(line_id)
            if line_block is None:
                logger.warning(f"[CalamariOcrBuilder] Line block not found: {line_id}")
                error_count += 1
                continue

            new_span = SpanClass(
                text=text.strip() + " ",
                formats=["plain"],
                page_id=page.page_id,
                polygon=line_block.polygon,
                minimum_position=0,
                maximum_position=0,
                font="Unknown",
                font_weight=0,
                font_size=0,
            )

            try:
                self._ocr_helper.replace_line_spans(document, page, line_block, [new_span])
                success_count += 1
            except Exception as e:
                logger.warning(f"[CalamariOcrBuilder] replace_line_spans failed for {line_id}: {e}")
                error_count += 1
                try:
                    self._fallback_replace_spans(document, page, line_block, new_span)
                    success_count += 1
                    error_count -= 1
                except Exception as e2:
                    logger.warning(f"[CalamariOcrBuilder] Fallback also failed: {e2}")

            try:
                line_block.set_internal_metadata("ocr_backend", "calamari")
            except Exception:
                pass

        logger.info(
            f"[CalamariOcrBuilder] Batch write complete: written={success_count}, "
            f"empty={empty_count}, errors={error_count}"
        )
