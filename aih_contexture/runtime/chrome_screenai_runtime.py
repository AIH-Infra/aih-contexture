from __future__ import annotations

from contextlib import contextmanager
import html
import gc
import threading
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import fitz
from PIL import Image

from aih_contexture.logger import get_logger
from aih_contexture.vendor.locro import ScreenAI
from aih_contexture.vendor.locro.models import OcrBlock, OcrPage

logger = get_logger()

ChromeProgressCallback = Callable[[dict[str, Any]], None]

_RASTER_PREPROCESS_MODES = {"strip_existing_ocr", "rasterize_pdf", "strip_then_rasterize"}


@dataclass
class _ChromePageResult:
    page_index: int
    markdown: str
    clean_html: str
    printed_page: str | None
    chunk_page: dict[str, Any]


def _chrome_result_to_payload(result: _ChromePageResult) -> dict[str, Any]:
    return {
        "page_index": result.page_index,
        "markdown": result.markdown,
        "clean_html": result.clean_html,
        "printed_page": result.printed_page,
        "chunk_page": result.chunk_page,
    }


def _chrome_result_from_payload(payload: dict[str, Any]) -> _ChromePageResult:
    return _ChromePageResult(
        page_index=int(payload["page_index"]),
        markdown=str(payload.get("markdown") or ""),
        clean_html=str(payload.get("clean_html") or ""),
        printed_page=payload.get("printed_page"),
        chunk_page=dict(payload.get("chunk_page") or {}),
    )


def _process_pdf_chunk_worker(
    pdf_path: str,
    page_indices: list[int],
    model_dir: str | None,
    light_mode: bool,
    preprocess_mode: str,
    rasterize_dpi: int,
    max_retries: int,
) -> list[dict[str, Any]]:
    runtime = ChromeScreenAIRuntime(
        model_dir=model_dir,
        light_mode=light_mode,
        preprocess_mode=preprocess_mode,
        workers=1,
        chunk_pages=max(1, len(page_indices)),
        batch_rest=0.0,
        rasterize_dpi=rasterize_dpi,
        emit_searchable_pdf=False,
        max_retries=max_retries,
        progress_callback=None,
    )
    results: list[dict[str, Any]] = []
    try:
        pdf = Path(pdf_path)
        for page_index in page_indices:
            result = runtime._ocr_pdf_page_with_retry(pdf, page_index, page_index)
            results.append(_chrome_result_to_payload(result))
    finally:
        runtime._close_thread_pdf_docs()
    return results


class ChromeScreenAIRuntime:
    def __init__(
        self,
        *,
        model_dir: str | None = None,
        light_mode: bool = False,
        preprocess_mode: str = "native",
        workers: int = 2,
        chunk_pages: int = 4,
        batch_rest: float = 0.0,
        rasterize_dpi: int = 144,
        emit_searchable_pdf: bool = False,
        max_retries: int = 1,
        progress_callback: ChromeProgressCallback | None = None,
    ) -> None:
        self.model_dir = Path(model_dir).expanduser() if model_dir else None
        self.light_mode = bool(light_mode)
        self.preprocess_mode = self.normalize_preprocess_mode(preprocess_mode)
        self.workers = max(1, int(workers))
        self.chunk_pages = max(1, int(chunk_pages))
        self.batch_rest = max(0.0, float(batch_rest))
        self.rasterize_dpi = max(72, int(rasterize_dpi))
        self.emit_searchable_pdf = bool(emit_searchable_pdf)
        self.max_retries = max(1, int(max_retries))
        self.progress_callback = progress_callback
        self._thread_local = threading.local()

    @staticmethod
    def normalize_preprocess_mode(value: Any) -> str:
        mode = str(value or "native").strip().lower().replace("-", "_")
        if mode in {"strip", "strip_ocr", "strip_existing_text"}:
            return "strip_existing_ocr"
        if mode in {"rasterize", "render"}:
            return "rasterize_pdf"
        if mode in {"strip_then_render", "strip_and_rasterize"}:
            return "strip_then_rasterize"
        if mode not in {"native", "strip_existing_ocr", "rasterize_pdf", "strip_then_rasterize"}:
            return "native"
        return mode

    def get_runtime_profile(self) -> dict[str, Any]:
        return {
            "official_protocol": "chrome_screenai_native",
            "model_family": "Chrome ScreenAI",
            "request_concurrency": self.workers,
            "preprocess_profile": self.preprocess_mode,
            "sampling_profile": "light" if self.light_mode else "standard",
            "image_transport": "native_pdf",
        }

    def process_document(self, filepath: str | Path, page_indices: list[int]) -> dict[str, Any]:
        path = Path(filepath)
        if path.suffix.lower() == ".pdf":
            return self._process_pdf(path, page_indices)
        return self._process_image(path)

    def _process_pdf(self, pdf_path: Path, page_indices: list[int]) -> dict[str, Any]:
        if not page_indices:
            return {
                "markdown_pages": [],
                "clean_html_pages": [],
                "printed_pages": [],
                "chunk_pages": [],
                "searchable_pdf_path": None,
            }

        ordered_results: list[_ChromePageResult] = []
        chunks = [
            page_indices[chunk_start:chunk_start + self.chunk_pages]
            for chunk_start in range(0, len(page_indices), self.chunk_pages)
        ]
        worker_count = max(1, min(self.workers, len(chunks)))
        for chunk in chunks:
            chunk_begin = chunk[0] + 1
            chunk_end = chunk[-1] + 1
            logger.info(
                "[Chrome ScreenAI] Processing chunk %s-%s/%s with %s worker(s)",
                chunk_begin,
                chunk_end,
                len(page_indices),
                worker_count,
            )
            self._emit_progress(
                event="render_batch",
                start_page=chunk_begin,
                end_page=chunk_end,
                stage="processing",
                backend="chrome_screenai",
                message=f"正在识别第 {chunk_begin}-{chunk_end} 页",
            )

        if worker_count == 1:
            self._process_chunks_sequential(pdf_path, chunks, ordered_results)
        else:
            try:
                with ProcessPoolExecutor(max_workers=worker_count) as pool:
                    future_map = {}
                    for chunk_index, chunk in enumerate(chunks):
                        future = pool.submit(
                            _process_pdf_chunk_worker,
                            str(pdf_path),
                            chunk,
                            str(self.model_dir) if self.model_dir is not None else None,
                            self.light_mode,
                            self.preprocess_mode,
                            self.rasterize_dpi,
                            self.max_retries,
                        )
                        future_map[future] = chunk
                        if chunk_index + 1 < len(chunks) and self.batch_rest > 0:
                            logger.info("[Chrome ScreenAI] Sleeping %.2fs between chunk submissions", self.batch_rest)
                            time.sleep(self.batch_rest)

                    for future in as_completed(future_map):
                        chunk_payloads = future.result()
                        for payload in chunk_payloads:
                            result = _chrome_result_from_payload(payload)
                            ordered_results.append(result)
                            self._emit_progress(
                                event="page_done",
                                page_num=result.page_index + 1,
                                ok=True,
                                stage="processing",
                                backend="chrome_screenai",
                            )
                        gc.collect()
            except Exception as exc:
                logger.warning(
                    "[Chrome ScreenAI] Parallel worker pool failed, falling back to sequential OCR: %s",
                    exc,
                )
                self._emit_progress(
                    event="parallel_fallback",
                    stage="processing",
                    backend="chrome_screenai",
                    ok=False,
                    message="并行处理失败，正在自动回退到串行模式",
                )
                ordered_results.clear()
                self._process_chunks_sequential(pdf_path, chunks, ordered_results)

        ordered_results.sort(key=lambda item: item.page_index)

        searchable_pdf_path = None
        if self.emit_searchable_pdf:
            output_pdf = pdf_path.with_name(f"{pdf_path.stem}.chrome-screenai.searchable.pdf")
            logger.info("[Chrome ScreenAI] Writing searchable PDF: %s", output_pdf)
            self._emit_progress(
                event="searchable_pdf",
                stage="saving",
                backend="chrome_screenai",
                output_pdf=str(output_pdf),
                message="正在生成可搜索 PDF",
            )
            self._write_searchable_pdf(pdf_path, ordered_results, page_indices, output_pdf)
            searchable_pdf_path = str(output_pdf)

        return {
            "markdown_pages": [result.markdown for result in ordered_results],
            "clean_html_pages": [result.clean_html for result in ordered_results],
            "printed_pages": [result.printed_page for result in ordered_results],
            "chunk_pages": [result.chunk_page for result in ordered_results],
            "searchable_pdf_path": searchable_pdf_path,
        }

    def _process_chunks_sequential(
        self,
        pdf_path: Path,
        chunks: list[list[int]],
        ordered_results: list[_ChromePageResult],
    ) -> None:
        try:
            for chunk_index, chunk in enumerate(chunks):
                for page_index in chunk:
                    result = self._ocr_pdf_page_with_retry(pdf_path, page_index, page_index)
                    ordered_results.append(result)
                    self._emit_progress(
                        event="page_done",
                        page_num=result.page_index + 1,
                        ok=True,
                        stage="processing",
                        backend="chrome_screenai",
                    )
                gc.collect()
                if chunk_index + 1 < len(chunks) and self.batch_rest > 0:
                    logger.info("[Chrome ScreenAI] Sleeping %.2fs between page chunks", self.batch_rest)
                    time.sleep(self.batch_rest)
        finally:
            self._close_thread_pdf_docs()

    def _process_image(self, image_path: Path) -> dict[str, Any]:
        with Image.open(image_path) as source_image:
            image = source_image.convert("RGB")
        page = self._get_screen_ai().ocr_pil_image(image)
        result = self._page_result_from_ocr_page(page_index=0, ocr_page=page)
        return {
            "markdown_pages": [result.markdown],
            "clean_html_pages": [result.clean_html],
            "printed_pages": [result.printed_page],
            "chunk_pages": [result.chunk_page],
            "searchable_pdf_path": None,
        }

    def _ocr_pdf_page_with_retry(self, pdf_path: Path, page_index: int, original_page_index: int) -> _ChromePageResult:
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                return self._ocr_pdf_page(pdf_path, page_index, original_page_index)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "[Chrome ScreenAI] Page %s attempt %s/%s failed: %s",
                    page_index + 1,
                    attempt,
                    self.max_retries,
                    exc,
                )
                if attempt >= self.max_retries:
                    raise
        assert last_error is not None
        raise last_error

    def _ocr_pdf_page(self, pdf_path: Path, page_index: int, original_page_index: int) -> _ChromePageResult:
        screen_ai = self._get_screen_ai()
        pil_image = self._render_pdf_page_for_ocr(
            pdf_path,
            page_index,
            max_dim=screen_ai.max_image_dimension,
        )
        ocr_page = screen_ai.ocr_pil_image(pil_image)
        return self._page_result_from_ocr_page(page_index=original_page_index, ocr_page=ocr_page)

    def _render_pdf_page_for_ocr(self, pdf_path: Path, page_index: int, *, max_dim: int) -> Image.Image:
        if self.preprocess_mode == "native":
            doc = self._get_thread_pdf_doc(pdf_path)
            return self._render_page(doc[page_index], max_dim=max_dim)
        if self.preprocess_mode == "rasterize_pdf":
            doc = self._get_thread_pdf_doc(pdf_path)
            return self._render_page(doc[page_index], dpi=self.rasterize_dpi)
        with self._open_stripped_doc(pdf_path, page_index) as stripped_doc:
            stripped_page = stripped_doc[0]
            if self.preprocess_mode == "strip_then_rasterize":
                return self._render_page(stripped_page, dpi=self.rasterize_dpi)
            return self._render_page(stripped_page, max_dim=max_dim)

    def _render_page(self, page: fitz.Page, *, max_dim: int | None = None, dpi: int | None = None) -> Image.Image:
        if dpi is None:
            assert max_dim is not None
            scale = min(1.0, float(max_dim) / max(page.rect.width, page.rect.height))
            dpi = max(72, int(72 * scale * 2))
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    def _page_result_from_ocr_page(self, *, page_index: int, ocr_page: OcrPage) -> _ChromePageResult:
        markdown = self._page_to_markdown(ocr_page)
        clean_html = self._page_to_html(ocr_page)
        printed_page = self._infer_printed_page(ocr_page)
        chunk_page = {
            "page_num": page_index,
            "img_size": [ocr_page.width, ocr_page.height],
            "backend": "chrome_screenai",
            "official_protocol": "chrome_screenai_native",
            "chunks": self._page_to_chunks(ocr_page),
            "ocr_result": self._page_to_raw_dict(ocr_page),
        }
        return _ChromePageResult(
            page_index=page_index,
            markdown=markdown,
            clean_html=clean_html,
            printed_page=printed_page,
            chunk_page=chunk_page,
        )

    def _page_to_chunks(self, page: OcrPage) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        for block_index, block in enumerate(page.blocks):
            chunk = {
                "label": "Text",
                "bbox": self._bbox_list(getattr(block, "bounding_box", None)),
                "content": self._block_to_html(block),
                "order": block_index,
                "lines": [],
            }
            for line_index, line in enumerate(block.lines):
                chunk["lines"].append(
                    {
                        "text": line.text,
                        "bbox": self._bbox_list(line.bounding_box),
                        "order": line_index,
                        "words": [
                            {
                                "text": word.text,
                                "confidence": word.confidence,
                                "bbox": self._bbox_list(word.bounding_box),
                            }
                            for word in line.words
                        ],
                    }
                )
            chunks.append(chunk)
        return chunks

    def _page_to_raw_dict(self, page: OcrPage) -> dict[str, Any]:
        return {
            "page_number": page.page_number,
            "width": page.width,
            "height": page.height,
            "blocks": [
                {
                    "block_type": block.block_type,
                    "bounding_box": self._bbox_object(getattr(block, "bounding_box", None)),
                    "lines": [
                        {
                            "text": line.text,
                            "bounding_box": self._bbox_object(line.bounding_box),
                            "words": [
                                {
                                    "text": word.text,
                                    "confidence": word.confidence,
                                    "bounding_box": self._bbox_object(word.bounding_box),
                                }
                                for word in line.words
                            ],
                        }
                        for line in block.lines
                    ],
                }
                for block in page.blocks
            ],
        }

    def _page_to_markdown(self, page: OcrPage) -> str:
        paragraphs = [self._block_to_text(block) for block in page.blocks]
        return "\n\n".join(text for text in paragraphs if text.strip())

    def _page_to_html(self, page: OcrPage) -> str:
        parts = ["<div class=\"chrome-screenai-page\">"]
        for block in page.blocks:
            text = self._block_to_text(block)
            if not text.strip():
                continue
            parts.append(f"<p>{html.escape(text).replace(chr(10), '<br/>')}</p>")
        parts.append("</div>")
        return "\n".join(parts)

    def _block_to_html(self, block: OcrBlock) -> str:
        return "<p>" + "<br/>".join(html.escape(line.text) for line in block.lines if line.text.strip()) + "</p>"

    def _block_to_text(self, block: OcrBlock) -> str:
        return "\n".join(line.text.strip() for line in block.lines if line.text and line.text.strip())

    def _infer_printed_page(self, page: OcrPage) -> str | None:
        if not page.height:
            return None
        page_height = float(page.height)
        candidates: list[tuple[float, str]] = []
        for block in page.blocks:
            for line in block.lines:
                bbox = line.bounding_box
                text = (line.text or "").strip()
                if bbox is None or not text or len(text) > 12:
                    continue
                lowered = text.lower()
                if not (text.isdigit() or (1 <= len(lowered) <= 8 and all(ch in "ivxlcdm" for ch in lowered))):
                    continue
                y = float(bbox.y)
                if y <= page_height * 0.14 or y >= page_height * 0.82:
                    candidates.append((abs((page_height * 0.5) - y), text))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def _write_searchable_pdf(
        self,
        pdf_path: Path,
        ordered_results: list[_ChromePageResult],
        page_indices: list[int],
        output_pdf: Path,
    ) -> None:
        page_map = {result.page_index: result for result in ordered_results}
        with fitz.open(pdf_path) as source_doc:
            output_doc = fitz.open()
            for page_index in page_indices:
                source_page = source_doc[page_index]
                target_page = output_doc.new_page(width=source_page.rect.width, height=source_page.rect.height)
                if self.preprocess_mode == "native":
                    target_page.show_pdf_page(target_page.rect, source_doc, page_index)
                elif self.preprocess_mode == "strip_existing_ocr":
                    with self._open_stripped_doc(pdf_path, page_index) as stripped_doc:
                        target_page.show_pdf_page(target_page.rect, stripped_doc, 0)
                else:
                    if self.preprocess_mode == "strip_then_rasterize":
                        with self._open_stripped_doc(pdf_path, page_index) as stripped_doc:
                            stripped_page = stripped_doc[0]
                            pix = stripped_page.get_pixmap(dpi=self.rasterize_dpi, alpha=False)
                    else:
                        pix = source_page.get_pixmap(dpi=self.rasterize_dpi, alpha=False)
                    target_page.insert_image(target_page.rect, stream=pix.tobytes("png"))
                result = page_map.get(page_index)
                if result is None:
                    continue
                ocr_result = result.chunk_page.get("ocr_result") if isinstance(result.chunk_page, dict) else None
                if not isinstance(ocr_result, dict):
                    continue
                width = float(ocr_result.get("width") or 0)
                height = float(ocr_result.get("height") or 0)
                if width <= 0 or height <= 0:
                    continue
                sx = float(target_page.rect.width) / width
                sy = float(target_page.rect.height) / height
                self._overlay_page_text_from_raw(target_page, ocr_result, sx, sy)
            output_doc.save(output_pdf, deflate=True)
            output_doc.close()

    def _overlay_page_text_from_raw(self, page: fitz.Page, ocr_result: dict[str, Any], sx: float, sy: float) -> None:
        blocks = ocr_result.get("blocks")
        if not isinstance(blocks, list):
            return
        for block in blocks:
            if not isinstance(block, dict):
                continue
            lines = block.get("lines")
            if not isinstance(lines, list):
                continue
            for line in lines:
                if isinstance(line, dict):
                    self._overlay_line_words_from_raw(page, line, sx, sy)

    def _overlay_line_words_from_raw(self, page: fitz.Page, line: dict[str, Any], sx: float, sy: float) -> None:
        words = line.get("words")
        if not isinstance(words, list):
            return
        for word in words:
            if not isinstance(word, dict):
                continue
            bbox = word.get("bounding_box")
            text = str(word.get("text") or "").strip()
            if not isinstance(bbox, dict) or not text:
                continue
            x = float(bbox.get("x") or 0)
            y = float(bbox.get("y") or 0)
            width = float(bbox.get("width") or 0)
            height = float(bbox.get("height") or 0)
            if width <= 0 or height <= 0:
                continue
            x0 = x * sx
            y0 = y * sy
            x1 = (x + width) * sx
            y1 = (y + height) * sy
            font_size = max(1.0, (y1 - y0) * 0.8)
            page.insert_text(
                fitz.Point(x0, y1 - font_size * 0.1),
                text,
                fontsize=font_size,
                render_mode=3,
            )

    def _get_screen_ai(self) -> ScreenAI:
        instance = getattr(self._thread_local, "screen_ai", None)
        if instance is None:
            kwargs: dict[str, Any] = {"light_mode": self.light_mode}
            if self.model_dir is not None:
                kwargs["model_dir"] = self.model_dir
            instance = ScreenAI(**kwargs)
            self._thread_local.screen_ai = instance
        return instance

    def _get_thread_pdf_doc(self, pdf_path: Path) -> fitz.Document:
        docs = getattr(self._thread_local, "pdf_docs", None)
        if docs is None:
            docs = {}
            self._thread_local.pdf_docs = docs
        key = str(pdf_path.resolve())
        doc = docs.get(key)
        if doc is None:
            doc = fitz.open(pdf_path)
            docs[key] = doc
        return doc

    def _close_thread_pdf_docs(self) -> None:
        docs = getattr(self._thread_local, "pdf_docs", None)
        if not isinstance(docs, dict):
            return
        for doc in docs.values():
            try:
                doc.close()
            except Exception as exc:
                logger.debug("[Chrome ScreenAI] ignored PDF close error: %s", exc)
        docs.clear()

    def _strip_text_layer(self, page: fitz.Page) -> None:
        words = page.get_text("words")
        if not words:
            return
        for word in words:
            if len(word) < 4:
                continue
            rect = fitz.Rect(word[:4])
            if rect.is_empty or rect.is_infinite:
                continue
            page.add_redact_annot(rect, fill=None, cross_out=False)
        page.apply_redactions(images=0, graphics=0, text=0)
        page.clean_contents()

    @contextmanager
    def _open_stripped_doc(self, pdf_path: Path, page_index: int):
        source_doc = self._get_thread_pdf_doc(pdf_path)
        temp_doc = fitz.open()
        try:
            temp_doc.insert_pdf(source_doc, from_page=page_index, to_page=page_index)
            self._strip_text_layer(temp_doc[0])
            yield temp_doc
        finally:
            temp_doc.close()

    def _emit_progress(self, **event: Any) -> None:
        if self.progress_callback is None:
            return
        try:
            self.progress_callback(event)
        except Exception as exc:
            logger.debug("[Chrome ScreenAI] progress callback ignored: %s", exc)

    @staticmethod
    def _bbox_list(box: Any) -> list[float] | None:
        if box is None:
            return None
        return [
            float(box.x),
            float(box.y),
            float(box.x + box.width),
            float(box.y + box.height),
        ]

    @staticmethod
    def _bbox_object(box: Any) -> dict[str, float] | None:
        if box is None:
            return None
        return {
            "x": float(box.x),
            "y": float(box.y),
            "width": float(box.width),
            "height": float(box.height),
            "angle": float(getattr(box, "angle", 0.0)),
        }
