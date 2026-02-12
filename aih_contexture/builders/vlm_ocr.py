import copy
from typing import Annotated, List, Optional, Tuple, Callable

from PIL import Image
from pydantic import BaseModel, Field

from aih_contexture.builders import BaseBuilder
from aih_contexture.builders.ocr import OcrBuilder
from aih_contexture.providers.pdf import PdfProvider
from aih_contexture.schema import BlockTypes
from aih_contexture.schema.document import Document
from aih_contexture.schema.groups.page import PageGroup
from aih_contexture.schema.registry import get_block_class
from aih_contexture.services.ocr_vlm import VlmOcrService
from aih_contexture.utils.api_key_pool import APIKeyPool
from aih_contexture.utils.concurrent_executor import OrderedConcurrentExecutor


class VlmOcrLine(BaseModel):
    text: str = Field(default="")


class VlmOcrResponse(BaseModel):
    lines: List[VlmOcrLine] = Field(default_factory=list)


class VlmOcrBuilder(BaseBuilder):
    """
    VLM OCR Builder:
    - 默认: per-block（按 Marker 原逻辑切块逐块 OCR）[3]
    - 可选: region-merge / full-page（实验用途，不默认开启）[7]
    """

    vlm_prompt: Annotated[str, "Prompt for OCR output."] = (
        "Transcribe exactly as seen. Preserve line breaks. Do not repeat. Stop at end of block."
    )

    vlm_timeout: Annotated[int, "Timeout seconds for VLM calls."] = 120
    vlm_max_retries: Annotated[int, "Max retries for VLM calls."] = 1
    min_block_area: Annotated[int, "Minimum block area (px²) to OCR."] = 400

    # 默认关闭整页与合并，避免混乱（你要求的行为）
    use_full_page_ocr: Annotated[bool, "Use full-page OCR mode."] = False
    full_page_max_tokens: Annotated[int, "Max tokens for full-page."] = 2048

    merge_enabled: Annotated[bool, "Enable region merge mode."] = False
    merge_y_threshold: Annotated[int, "Y threshold for merging."] = 80
    merge_max_blocks: Annotated[int, "Max blocks per group."] = 15
    merge_x_margin: Annotated[int, "X margin for merged crop."] = 20

    noise_tokens: Annotated[List[str], "Text snippets to filter out."] = [
        "{...}", "{ ...}", "{}", "{", "}", "...",
    ]

    # 并发配置（新增）
    enable_concurrent: Annotated[bool, "Enable concurrent OCR processing."] = True
    max_concurrent: Annotated[int, "Maximum concurrent OCR requests."] = 3

    progress_callback: Optional[Callable[[int, int, str], None]] = None

    def __init__(self, llm_service: Optional[VlmOcrService], config=None):
        super().__init__(config)
        self.config = config or {}
        if llm_service is None:
            raise ValueError("VlmOcrBuilder requires OpenAIService.")
        self.llm_service = llm_service
        self._ocr_helper = OcrBuilder(recognition_model=None, config=self.config)

        if isinstance(config, dict):
            self.vlm_prompt = config.get("vlm_prompt", self.vlm_prompt)
            self.use_full_page_ocr = bool(config.get("vlm_full_page_ocr", self.use_full_page_ocr))
            self.full_page_max_tokens = int(config.get("vlm_full_page_max_tokens", self.full_page_max_tokens))

            self.merge_enabled = bool(config.get("vlm_merge_enabled", self.merge_enabled))
            self.merge_y_threshold = int(config.get("vlm_merge_y_threshold", self.merge_y_threshold))
            self.merge_max_blocks = int(config.get("vlm_merge_max_blocks", self.merge_max_blocks))

            # 并发配置
            self.enable_concurrent = bool(config.get("vlm_ocr_enable_concurrent", self.enable_concurrent))
            self.max_concurrent = int(config.get("openai_max_concurrent", config.get("vlm_ocr_max_concurrent", self.max_concurrent)))

        # 初始化KeyPool和Executor（用于并发）
        if self.enable_concurrent and hasattr(self.llm_service, 'openai_api_key'):
            try:
                self.key_pool = APIKeyPool(self.llm_service.openai_api_key)
                self.executor = OrderedConcurrentExecutor(
                    self.key_pool,
                    max_concurrent=self.max_concurrent,
                    retry_on_failure=True,
                    max_retries=int(self.vlm_max_retries)
                )
                from aih_contexture.logger import get_logger
                logger = get_logger()
                logger.info(
                    f"[VlmOcrBuilder] Concurrent mode enabled: "
                    f"{self.key_pool.get_key_count()} keys, max_concurrent={self.max_concurrent}"
                )
            except Exception as e:
                from aih_contexture.logger import get_logger
                logger = get_logger()
                logger.warning(f"[VlmOcrBuilder] Failed to initialize concurrent mode: {e}, falling back to serial")
                self.enable_concurrent = False
                self.key_pool = None
                self.executor = None
        else:
            self.key_pool = None
            self.executor = None

    def __call__(self, document: Document, provider: PdfProvider):
        from aih_contexture.logger import get_logger
        logger = get_logger()

        pages_to_ocr = [p for p in document.pages if p.text_extraction_method == "surya"]
        if not pages_to_ocr:
            logger.info("[VlmOcrBuilder] No pages need OCR")
            return

        total_pages = len(pages_to_ocr)
        logger.info(
            "[VlmOcrBuilder] pages=%d, mode=%s",
            total_pages,
            "full_page" if self.use_full_page_ocr else ("merge" if self.merge_enabled else "tile"),
        )

        # 可选：整页（默认关闭）
        if self.use_full_page_ocr:
            for page_idx, page in enumerate(pages_to_ocr):
                if self.progress_callback:
                    self.progress_callback(page_idx + 1, total_pages, f"OCR page {page.page_id}")
                self._ocr_full_page(page, provider)
            return

        # 默认：按 Marker 原逻辑切块逐块 OCR（用 OcrBuilder 的 polygon/id 选择逻辑）[3]
        page_images, _, block_ids, _ = self._ocr_helper.get_ocr_images_polygons_ids(document, pages_to_ocr, provider)
        if not any(block_ids):
            logger.info("[VlmOcrBuilder] No blocks need OCR")
            return

        for page_idx, (page, page_image, page_block_ids) in enumerate(zip(pages_to_ocr, page_images, block_ids)):
            if self.progress_callback:
                self.progress_callback(page_idx + 1, total_pages, f"OCR page {page.page_id}")

            if self.merge_enabled and len(page_block_ids) > 1:
                self._ocr_page_merged(page, page_image, page_block_ids, provider)
            else:
                self._ocr_page_single(page, page_image, page_block_ids, provider)

    def _ocr_full_page(self, page: PageGroup, provider: PdfProvider):
        from aih_contexture.logger import get_logger
        logger = get_logger()

        page_image = page.get_image(highres=True)
        if page_image is None:
            return

        original_max = getattr(self.llm_service, "max_output_tokens", 2048)
        self.llm_service.max_output_tokens = int(self.full_page_max_tokens)
        try:
            result = self.llm_service(
                prompt=self.vlm_prompt,
                image=page_image,
                block=None,
                response_schema=VlmOcrResponse,
                max_retries=int(self.vlm_max_retries),
                timeout=int(self.vlm_timeout),
            )
        except Exception as e:
            logger.error(f"[VlmOcrBuilder] Full-page VLM failed: {e}")
            return
        finally:
            self.llm_service.max_output_tokens = original_max

        raw_lines = (result or {}).get("lines") or []
        lines = []
        for item in raw_lines:
            if isinstance(item, dict):
                t = (item.get("text") or "").strip()
            elif isinstance(item, str):
                t = item.strip()
            else:
                continue
            if t and not self._is_noise(t):
                lines.append(t)

        if not lines:
            return

        # 粗略写回：整页模式会引入映射复杂度，所以仅作为实验用途
        # 将整页文本写入第一个 Text block（避免破坏结构）
        for block_id in page.structure:
            block = page.get_block(block_id)
            if block and block.block_type in (BlockTypes.Text, BlockTypes.Footnote, BlockTypes.SectionHeader, BlockTypes.ListItem):
                SpanClass = get_block_class(BlockTypes.Span)
                LineClass = get_block_class(BlockTypes.Line)
                self._write_lines_to_block(page, block, lines, SpanClass, LineClass)
                break

    def _ocr_page_single(
        self,
        page: PageGroup,
        page_image: Image.Image,
        page_block_ids: List[str],
        provider: PdfProvider,
    ):
        from aih_contexture.logger import get_logger
        logger = get_logger()

        page_size = provider.get_page_bbox(page.page_id).size
        image_size = page_image.size

        SpanClass = get_block_class(BlockTypes.Span)
        LineClass = get_block_class(BlockTypes.Line)

        # 准备block数据（预处理）
        block_data_list = []
        for block_id in page_block_ids:
            block = page.get_block(block_id)
            if block is None:
                continue

            block_polygon_rescaled = (
                copy.deepcopy(block.polygon)
                .rescale(page_size, image_size)
                .fit_to_bounds((0, 0, *image_size))
            )
            crop_bbox = tuple(int(x) for x in block_polygon_rescaled.bbox)

            w = crop_bbox[2] - crop_bbox[0]
            h = crop_bbox[3] - crop_bbox[1]
            if (w * h) < self.min_block_area:
                continue

            crop_img = page_image.crop(crop_bbox)
            block_data_list.append((block_id, block, crop_img))

        if not block_data_list:
            return

        # 并发模式：使用OrderedConcurrentExecutor
        if self.enable_concurrent and self.executor:
            # 创建任务列表
            tasks = []
            for block_id, block, crop_img in block_data_list:
                def make_task(b, img):
                    def task(api_key):
                        try:
                            return self.llm_service.call_with_key(
                                api_key=api_key,
                                prompt=self.vlm_prompt,
                                image=img,
                                block=b,
                                response_schema=VlmOcrResponse,
                                max_retries=int(self.vlm_max_retries),
                                timeout=int(self.vlm_timeout),
                            )
                        except Exception as e:
                            logger.error(f"[VlmOcrBuilder] VLM failed for {b.id}: {e}")
                            return None
                    return task
                tasks.append(make_task(block, crop_img))

            # 并发执行，保证顺序
            results = self.executor.execute_sync(
                tasks,
                preserve_order=True,
                desc=f"OCR page {page.page_id}",
                disable_progress=True  # 外层已有进度条
            )

            # 按顺序写回结果
            for (block_id, block, _), result in zip(block_data_list, results):
                if result is None:
                    continue

                raw_lines = (result or {}).get("lines") or []
                lines: List[str] = []
                for item in raw_lines:
                    if isinstance(item, dict):
                        t = (item.get("text") or "").strip()
                    elif isinstance(item, str):
                        t = item.strip()
                    else:
                        continue
                    if t and not self._is_noise(t):
                        lines.append(t)

                if not lines:
                    continue

                self._write_lines_to_block(page, block, lines, SpanClass, LineClass)

        # 串行模式：保持原有逻辑（向后兼容）
        else:
            for block_id, block, crop_img in block_data_list:
                try:
                    result = self.llm_service(
                        prompt=self.vlm_prompt,
                        image=crop_img,
                        block=block,
                        response_schema=VlmOcrResponse,
                        max_retries=int(self.vlm_max_retries),
                        timeout=int(self.vlm_timeout),
                    )
                except Exception as e:
                    logger.error(f"[VlmOcrBuilder] VLM failed for {block_id}: {e}")
                    continue

                raw_lines = (result or {}).get("lines") or []
                lines: List[str] = []
                for item in raw_lines:
                    if isinstance(item, dict):
                        t = (item.get("text") or "").strip()
                    elif isinstance(item, str):
                        t = item.strip()
                    else:
                        continue
                    if t and not self._is_noise(t):
                        lines.append(t)

                if not lines:
                    continue

                self._write_lines_to_block(page, block, lines, SpanClass, LineClass)

    def _ocr_page_merged(
        self,
        page: PageGroup,
        page_image: Image.Image,
        page_block_ids: List[str],
        provider: PdfProvider,
    ):
        from aih_contexture.logger import get_logger
        logger = get_logger()

        page_size = provider.get_page_bbox(page.page_id).size
        image_size = page_image.size

        groups = self._merge_blocks_by_region(page, page_block_ids, page_size, image_size)
        SpanClass = get_block_class(BlockTypes.Span)
        LineClass = get_block_class(BlockTypes.Line)

        for group_block_ids in groups:
            merged_bbox = self._get_merged_bbox(page, group_block_ids, page_size, image_size)
            crop_img = page_image.crop(merged_bbox)

            try:
                result = self.llm_service(
                    prompt=self.vlm_prompt,
                    image=crop_img,
                    block=None,
                    response_schema=VlmOcrResponse,
                    max_retries=int(self.vlm_max_retries),
                    timeout=int(self.vlm_timeout),
                )
            except Exception as e:
                logger.error(f"[VlmOcrBuilder] VLM failed for merged group: {e}")
                continue

            raw_lines = (result or {}).get("lines") or []
            lines: List[str] = []
            for item in raw_lines:
                if isinstance(item, dict):
                    t = (item.get("text") or "").strip()
                elif isinstance(item, str):
                    t = item.strip()
                else:
                    continue
                if t and not self._is_noise(t):
                    lines.append(t)

            if not lines:
                continue

            # 简单分配：按 block 顺序均分（仅实验用途）
            per = max(1, len(lines) // max(1, len(group_block_ids)))
            idx = 0
            for bid in group_block_ids:
                b = page.get_block(bid)
                if not b:
                    continue
                chunk = lines[idx: idx + per]
                idx += per
                if chunk:
                    self._write_lines_to_block(page, b, chunk, SpanClass, LineClass)

    def _merge_blocks_by_region(
        self,
        page: PageGroup,
        page_block_ids: List[str],
        page_size: Tuple[float, float],
        image_size: Tuple[int, int],
    ) -> List[List[str]]:
        block_infos = []
        for bid in page_block_ids:
            block = page.get_block(bid)
            if block is None:
                continue
            poly = copy.deepcopy(block.polygon).rescale(page_size, image_size)
            bbox = poly.bbox
            y_center = (bbox[1] + bbox[3]) / 2
            block_infos.append((bid, y_center))

        block_infos.sort(key=lambda x: x[1])
        groups: List[List[str]] = []
        cur: List[str] = []
        last_y = None

        for bid, y in block_infos:
            if last_y is None:
                cur = [bid]
                last_y = y
                continue
            if (y - last_y) < self.merge_y_threshold and len(cur) < self.merge_max_blocks:
                cur.append(bid)
            else:
                groups.append(cur)
                cur = [bid]
            last_y = y

        if cur:
            groups.append(cur)
        return groups

    def _get_merged_bbox(
        self,
        page: PageGroup,
        block_ids: List[str],
        page_size: Tuple[float, float],
        image_size: Tuple[int, int],
    ) -> Tuple[int, int, int, int]:
        x0, y0, x1, y1 = float("inf"), float("inf"), 0, 0
        for bid in block_ids:
            block = page.get_block(bid)
            if block is None:
                continue
            poly = copy.deepcopy(block.polygon).rescale(page_size, image_size)
            bx0, by0, bx1, by1 = poly.bbox
            x0 = min(x0, bx0)
            y0 = min(y0, by0)
            x1 = max(x1, bx1)
            y1 = max(y1, by1)

        x0 = max(0, int(x0) - self.merge_x_margin)
        x1 = min(image_size[0], int(x1) + self.merge_x_margin)
        return (x0, int(y0), x1, int(y1))

    def _write_lines_to_block(
        self,
        page: PageGroup,
        block,
        lines: List[str],
        SpanClass,
        LineClass,
    ):
        # 兼容优先：text_extraction_method 只能是 pdftext/surya/gemini [5]
        try:
            block.set_internal_metadata("ocr_backend", "vlm")
        except Exception:
            pass

        if block.block_type == BlockTypes.Line:
            new_spans = [
                SpanClass(
                    text=" ".join(lines).rstrip("\n") + " ",
                    formats=["plain"],
                    page_id=page.page_id,
                    polygon=block.polygon,
                    minimum_position=0,
                    maximum_position=0,
                    font="Unknown",
                    font_weight=0,
                    font_size=0,
                )
            ]
            self._ocr_helper.replace_line_spans(None, page, block, new_spans)
            return

        for old_line in block.contained_blocks(page, block_types=[BlockTypes.Line]):
            old_line.removed = True
        block.structure = []

        for t in lines:
            span = SpanClass(
                text=t.rstrip("\n") + " ",
                formats=["plain"],
                page_id=page.page_id,
                polygon=block.polygon,
                minimum_position=0,
                maximum_position=0,
                font="Unknown",
                font_weight=0,
                font_size=0,
            )
            new_line = LineClass(
                polygon=block.polygon,
                page_id=block.page_id,
                text_extraction_method="surya",
            )
            page.add_full_block(new_line)
            block.add_structure(new_line)
            page.add_full_block(span)
            new_line.structure = [span.id]

    def _is_noise(self, text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return True
        if t in self.noise_tokens:
            return True
        return False