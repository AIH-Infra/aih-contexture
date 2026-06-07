"""
Calamari OCR Service - HTTP client for Calamari OCR Docker API

Key fix: 
1. ocr_page() - 整页作为一个批次发送，不拆分
2. ocr_batch() - 保留原有逻辑用于其他场景
"""

import io
import re
import time
from typing import Annotated, List, Optional

import requests
from PIL import Image

from aih_contexture.logger import get_logger
from aih_contexture.services import BaseService

logger = get_logger()


class CalamariOcrService(BaseService):
    calamari_base_url: Annotated[str, "Calamari API base URL."] = "http://localhost:11800"
    calamari_model: Annotated[str, "Model name to use."] = "gt4histocr"
    calamari_batch_size: Annotated[int, "Batch size for /ocr/batch (deprecated for page mode)."] = 100
    calamari_timeout: Annotated[int, "HTTP timeout seconds."] = 300  # 增加超时时间
    calamari_max_retries: Annotated[int, "Max retries for HTTP requests."] = 2

    calamari_sequential_mode: Annotated[bool, "Use /ocr sequentially instead of /ocr/batch."] = False
    calamari_trust_batch_order: Annotated[bool, "Trust that batch API returns results in request order."] = False

    calamari_require_ordering_info: Annotated[
        bool, "Require ordering info (filenames/results with index) in batch responses."
    ] = True

    calamari_fallback_to_sequential_on_ordering_failure: Annotated[
        bool, "Fallback to sequential OCR for a batch if ordering cannot be guaranteed."
    ] = True
    calamari_split_large_batches: Annotated[
        bool, "Split large ordered batches by calamari_batch_size while preserving filename indices."
    ] = True

    def __init__(self, config=None):
        super().__init__(config)
        config = config or {}

        self.calamari_base_url = config.get("calamari_base_url", self.calamari_base_url)
        self.calamari_model = config.get("calamari_model", self.calamari_model)
        self.calamari_batch_size = int(config.get("calamari_batch_size", self.calamari_batch_size))
        self.calamari_timeout = int(config.get("calamari_timeout", self.calamari_timeout))
        self.calamari_max_retries = int(config.get("calamari_max_retries", self.calamari_max_retries))

        self.calamari_sequential_mode = bool(config.get("calamari_sequential_mode", self.calamari_sequential_mode))
        self.calamari_trust_batch_order = bool(config.get("calamari_trust_batch_order", self.calamari_trust_batch_order))

        self.calamari_require_ordering_info = bool(
            config.get("calamari_require_ordering_info", self.calamari_require_ordering_info)
        )
        self.calamari_fallback_to_sequential_on_ordering_failure = bool(
            config.get(
                "calamari_fallback_to_sequential_on_ordering_failure",
                self.calamari_fallback_to_sequential_on_ordering_failure,
            )
        )
        self.calamari_split_large_batches = bool(
            config.get("calamari_split_large_batches", self.calamari_split_large_batches)
        )

        logger.info(
            f"[CalamariOcrService] Init: base_url={self.calamari_base_url}, model={self.calamari_model}, "
            f"timeout={self.calamari_timeout}, sequential_mode={self.calamari_sequential_mode}"
        )

    def health_check(self) -> bool:
        try:
            resp = requests.get(f"{self.calamari_base_url}/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def ocr_page(self, images: List[Image.Image], global_start_index: int = 0) -> List[str]:
        """
        🔑 核心方法：整页所有行作为一个批次发送

        - 不按 batch_size 拆分
        - 保证返回顺序与输入顺序一致
        - 支持降级到 sequential 模式

        Args:
            images: 行图片列表
            global_start_index: 全局起始索引（用于多页批处理）
        """
        if not images:
            return []

        if self.calamari_sequential_mode:
            logger.info(f"[CalamariOcrService] Using sequential mode for {len(images)} images")
            return self._ocr_sequential(images)

        logger.info(
            f"[CalamariOcrService] Using batch mode for {len(images)} images, "
            f"global_start_index={global_start_index}"
        )

        if self.calamari_split_large_batches and len(images) > self.calamari_batch_size:
            return self._ocr_ordered_chunks(images, global_start_index=global_start_index)

        # 直接发送，使用全局索引
        return self._ocr_batch_single(images, global_start_index=global_start_index)

    def ocr_batch(self, images: List[Image.Image]) -> List[str]:
        """
        兼容方法：按 batch_size 拆分发送（保留原有逻辑）
        
        ⚠️ 不推荐使用！可能导致跨批次顺序问题
        """
        if not images:
            return []

        if self.calamari_sequential_mode:
            logger.info(f"[CalamariOcrService] Using sequential mode for {len(images)} images")
            return self._ocr_sequential(images)

        logger.info(f"[CalamariOcrService] Using BATCH mode for {len(images)} images (may split)")

        results: List[str] = []
        global_start = 0
        while global_start < len(images):
            chunk = images[global_start : global_start + self.calamari_batch_size]
            chunk_results = self._ocr_batch_single(chunk, global_start_index=global_start)
            results.extend(chunk_results)
            global_start += len(chunk)

        return results

    def _ocr_ordered_chunks(self, images: List[Image.Image], global_start_index: int) -> List[str]:
        """Split a large logical batch without losing global filename ordering."""
        results: List[str] = []
        offset = 0
        total = len(images)
        logger.info(
            f"[CalamariOcrService] Splitting ordered batch: total={total}, batch_size={self.calamari_batch_size}"
        )
        while offset < total:
            chunk = images[offset : offset + self.calamari_batch_size]
            chunk_start = global_start_index + offset
            logger.info(
                f"[CalamariOcrService] Ordered chunk: {offset + 1}-{offset + len(chunk)}/{total}, "
                f"global_start_index={chunk_start}"
            )
            results.extend(self._ocr_batch_single(chunk, global_start_index=chunk_start))
            offset += len(chunk)
        return results

    def _ocr_sequential(self, images: List[Image.Image]) -> List[str]:
        """串行模式：逐张发送"""
        out: List[str] = []
        total = len(images)
        logger.info(f"[CalamariOcrService] Sequential OCR: 0/{total}")

        for idx, img in enumerate(images):
            if idx % 20 == 0 or idx == total - 1:
                logger.info(f"[CalamariOcrService] Sequential progress: {idx + 1}/{total}")

            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)

            files = {"file": ("image.png", buf.getvalue(), "image/png")}
            data = {"model": self.calamari_model}

            try:
                resp = requests.post(
                    f"{self.calamari_base_url}/ocr",
                    files=files,
                    data=data,
                    timeout=self.calamari_timeout
                )
                resp.raise_for_status()
                payload = resp.json()
                out.append((payload.get("text") or "").strip())
            except Exception as e:
                logger.warning(f"[CalamariOcrService] Sequential OCR failed for image {idx}: {e}")
                out.append("")

        logger.info(f"[CalamariOcrService] Sequential complete: {total} images")
        return out

    def _ocr_batch_single(self, images: List[Image.Image], global_start_index: int) -> List[str]:
        """处理单个批次的 OCR"""
        index_to_position = {global_start_index + i: i for i in range(len(images))}

        logger.info(
            f"[CalamariOcrService] _ocr_batch_single: "
            f"images={len(images)}, global_start_index={global_start_index}"
        )

        for attempt in range(1, self.calamari_max_retries + 2):
            try:
                files = []
                for i, img in enumerate(images):
                    global_idx = global_start_index + i
                    filename = f"image_{global_idx:06d}.png"
                    buf = io.BytesIO()
                    img.save(buf, format="PNG")
                    buf.seek(0)
                    files.append(("files", (filename, buf.getvalue(), "image/png")))

                data = {"model": self.calamari_model}

                logger.info(f"[CalamariOcrService] Sending batch to {self.calamari_base_url}/ocr/batch")

                resp = requests.post(
                    f"{self.calamari_base_url}/ocr/batch",
                    files=files,
                    data=data,
                    timeout=self.calamari_timeout,
                )
                resp.raise_for_status()
                payload = resp.json()

                logger.info(f"[CalamariOcrService] Response keys: {list(payload.keys())}")
                if "results" in payload:
                    logger.info(f"[CalamariOcrService] Results count: {len(payload.get('results', []))}")
                    if payload.get("results"):
                        first_result = payload['results'][0]
                        logger.info(f"[CalamariOcrService] First result: filename={first_result.get('filename')}, text_preview={first_result.get('text', '')[:50]}...")

                try:
                    return self._parse_and_reorder_results(
                        payload,
                        expected_count=len(images),
                        global_start_index=global_start_index,
                        index_to_position=index_to_position,
                    )
                except Exception as ordering_error:
                    logger.error(
                        f"[CalamariOcrService] ❌ Batch ordering failed: {ordering_error}. "
                        f"global_start_index={global_start_index}, count={len(images)}"
                    )
                    if self.calamari_fallback_to_sequential_on_ordering_failure:
                        logger.warning(
                            f"[CalamariOcrService] ⚠️ Falling back to sequential OCR for this batch (count={len(images)})"
                        )
                        return self._ocr_sequential(images)
                    return [""] * len(images)

            except Exception as e:
                logger.warning(f"[CalamariOcrService] Batch attempt {attempt} failed: {e}")
                if attempt <= self.calamari_max_retries:
                    time.sleep(1.0)
                    continue
                
                # 最后一次尝试失败，降级到串行
                if self.calamari_fallback_to_sequential_on_ordering_failure:
                    logger.warning(f"[CalamariOcrService] ⚠️ All batch attempts failed, falling back to sequential")
                    return self._ocr_sequential(images)
                return [""] * len(images)

        return [""] * len(images)

    def _extract_index_from_filename(self, filename: str) -> Optional[int]:
        """从文件名中提取索引号"""
        if not filename:
            return None
        m = re.search(r"image_(\d+)", filename)
        if m:
            try:
                return int(m.group(1))
            except Exception:
                return None
        m2 = re.match(r"^(\d+)", filename)
        if m2:
            try:
                return int(m2.group(1))
            except Exception:
                return None
        return None

    def _parse_and_reorder_results(
        self,
        result: dict,
        expected_count: int,
        global_start_index: int,
        index_to_position: dict,
    ) -> List[str]:
        """解析批量响应并按索引重排结果"""
        ordered_results: List[Optional[str]] = [None] * expected_count
        expected_indices = set(index_to_position.keys())

        # 格式1: results 结构化数组（推荐格式）
        if isinstance(result, dict) and "results" in result:
            results_list = result.get("results") or []
            if not isinstance(results_list, list):
                raise ValueError("Invalid batch response: results must be a list")

            filled_positions = set()

            for item in results_list:
                if not isinstance(item, dict):
                    continue
                filename = item.get("filename")
                text = item.get("text")
                idx = item.get("index")

                if idx is None and filename:
                    idx = self._extract_index_from_filename(filename)

                if isinstance(idx, int) and idx in index_to_position:
                    pos = index_to_position[idx]
                    ordered_results[pos] = (text or "").strip()
                    filled_positions.add(pos)
                else:
                    logger.warning(f"[CalamariOcrService] Cannot map result: filename={filename}, idx={idx}")

            if self.calamari_require_ordering_info:
                if len(filled_positions) != expected_count:
                    missing_positions = sorted(set(range(expected_count)) - filled_positions)
                    raise ValueError(
                        f"Structured batch results could not be fully mapped "
                        f"(filled={len(filled_positions)}/{expected_count}, missing_sample={missing_positions[:10]})"
                    )

            return [v if v is not None else "" for v in ordered_results]

        # 格式2: filenames + texts 并行数组
        if isinstance(result, dict) and "filenames" in result and "texts" in result:
            filenames = result.get("filenames") or []
            texts = result.get("texts") or []
            if not isinstance(filenames, list) or not isinstance(texts, list):
                raise ValueError("Invalid batch response: filenames/texts must be lists")

            filled_positions = set()

            for filename, text in zip(filenames, texts):
                idx = self._extract_index_from_filename(filename)
                if idx is not None and idx in index_to_position:
                    pos = index_to_position[idx]
                    ordered_results[pos] = (text or "").strip()
                    filled_positions.add(pos)

            if self.calamari_require_ordering_info:
                if len(filled_positions) != expected_count:
                    missing_positions = sorted(set(range(expected_count)) - filled_positions)
                    raise ValueError(
                        f"Batch response filenames could not be fully mapped "
                        f"(filled={len(filled_positions)}/{expected_count}, missing_sample={missing_positions[:10]})"
                    )

            return [v if v is not None else "" for v in ordered_results]

        # 格式3: texts only（不保证顺序）
        if isinstance(result, dict) and "texts" in result:
            texts = result.get("texts") or []
            if not isinstance(texts, list):
                raise ValueError("Invalid batch response: texts must be a list")

            if self.calamari_require_ordering_info:
                raise ValueError(
                    "Batch response has texts only; no filenames/results to guarantee ordering."
                )

            if self.calamari_trust_batch_order:
                return [(t or "").strip() for t in texts[:expected_count]] + [""] * max(0, expected_count - len(texts))

            logger.warning("[CalamariOcrService] Response has no ordering info. Results may be misaligned.")
            return [(t or "").strip() for t in texts[:expected_count]] + [""] * max(0, expected_count - len(texts))

        raise ValueError(f"Unknown batch response format: keys={list(result.keys()) if isinstance(result, dict) else type(result)}")
# Backward compatibility alias
CalamariService = CalamariOcrService
