from __future__ import annotations

from typing import Any, Callable

from aih_contexture.backends.layout import default_layout_registry
from aih_contexture.backends.ocr import default_ocr_registry
from aih_contexture.builders.layout import LayoutBuilder
from aih_contexture.builders.ocr import OcrBuilder


class DisabledOcrBuilder:
    """No-op OCR builder used when OCR is explicitly disabled."""

    def __call__(self, document, provider):
        return document


def normalize_layout_backend_name(name: str | None) -> str:
    normalized = (name or "surya").strip().lower().replace("-", "_")
    if normalized == "vlm":
        return "vlm_layout"
    return normalized


def normalize_ocr_backend_name(name: str | None) -> str:
    normalized = (name or "surya").strip().lower().replace("-", "_")
    if normalized == "vlm":
        return "vlm_ocr"
    return normalized


def create_layout_builder(
    *,
    config: dict[str, Any],
    resolve_dependencies: Callable[[Any], Any],
    logger,
    layout_builder_class=LayoutBuilder,
):
    layout_backend = normalize_layout_backend_name(config.get("layout_backend", "surya"))

    if layout_backend == "yolo":
        raise ValueError(
            "layout_backend='yolo' has been removed from Contexture. "
            "Use 'surya' now, or migrate to the planned MinerU/Paddle layout adapters."
        )

    layout_spec = default_layout_registry.get(layout_backend)
    if not layout_spec.capabilities.implemented:
        raise ValueError(
            f"Layout backend '{layout_backend}' is declared but not implemented yet. "
            "Install or implement the adapter before selecting it for conversion."
        )

    if layout_backend == "vlm_layout":
        from aih_contexture.builders.vlm_layout import VlmLayoutBuilder
        from aih_contexture.services.layout_vlm import VlmLayoutService

        logger.info("[PdfConverter] Using VLM layout backend")
        try:
            vlm_layout_service = VlmLayoutService(config)
            layout_builder = VlmLayoutBuilder(vlm_layout_service, config=config)
            logger.info("[PdfConverter] VlmLayoutBuilder created")
            return layout_builder
        except Exception as e:
            logger.exception("[PdfConverter] VLM layout init failed: %s", e)
            logger.warning("[PdfConverter] Falling back to Surya layout")
            return resolve_dependencies(layout_builder_class)

    if layout_backend == "external_layout_sidecar":
        from aih_contexture.builders.external_layout_sidecar import ExternalLayoutSidecarBuilder

        logger.info("[PdfConverter] Using external layout sidecar backend")
        return ExternalLayoutSidecarBuilder(config=config)

    if layout_backend == "mineru_pp_doclayout_v2":
        from aih_contexture.builders.mineru_layout import MineruLayoutBuilder

        logger.info("[PdfConverter] Using MinerU Pipeline Sidecar layout backend (middle.json)")
        return MineruLayoutBuilder(config=config)

    if layout_backend == "mineru_pp_doclayout_v2_direct":
        from aih_contexture.builders.mineru_direct_layout import MineruDirectLayoutBuilder

        logger.info("[PdfConverter] Using MinerU PP-DocLayoutV2 Direct layout-only backend")
        return MineruDirectLayoutBuilder(config=config)

    if layout_backend in ("paddle_pp_doclayout_plus_l", "paddle_pp_doclayout_v3"):
        from aih_contexture.builders.paddle_layout import PaddleLayoutDetectionBuilder

        model_name = "PP-DocLayoutV3" if layout_backend == "paddle_pp_doclayout_v3" else "PP-DocLayout_plus-L"
        paddle_config = dict(config)
        paddle_config.setdefault("paddle_layout_model_name", model_name)
        logger.info("[PdfConverter] Using Paddle %s layout backend", model_name)
        return PaddleLayoutDetectionBuilder(config=paddle_config)

    logger.info("[PdfConverter] Using Surya layout backend")
    return resolve_dependencies(layout_builder_class)


def create_ocr_builder(
    *,
    config: dict[str, Any],
    resolve_dependencies: Callable[[Any], Any],
    logger,
    ocr_builder_class=OcrBuilder,
):
    ocr_backend = normalize_ocr_backend_name(config.get("ocr_backend", "surya"))
    disable_ocr = bool(config.get("disable_ocr", False))

    if disable_ocr:
        logger.info("[PdfConverter] OCR disabled, using PDF embedded text")
        return DisabledOcrBuilder()

    ocr_spec = default_ocr_registry.get(ocr_backend)
    if not ocr_spec.capabilities.implemented:
        raise ValueError(
            f"OCR backend '{ocr_backend}' is declared but not implemented yet. "
            "Install or implement the adapter before selecting it for conversion."
        )

    def fallback_to_surya_ocr():
        config.pop("ocr_line_source", None)
        return resolve_dependencies(ocr_builder_class)

    if ocr_backend == "vlm_ocr":
        from aih_contexture.builders.vlm_ocr import VlmOcrBuilder
        from aih_contexture.services.ocr_vlm import VlmOcrService

        logger.warning("[PdfConverter] Using VLM OCR backend")
        try:
            openai_service = VlmOcrService(config)
            ocr_builder = VlmOcrBuilder(openai_service, config=config)
            logger.info("[PdfConverter] VlmOcrBuilder created")
            return ocr_builder
        except Exception as e:
            logger.exception("[PdfConverter] VLM OCR init failed: %s", e)
            logger.warning("[PdfConverter] Falling back to Surya OCR")
            return fallback_to_surya_ocr()

    if ocr_backend == "calamari":
        from aih_contexture.builders.calamari_ocr import CalamariOcrBuilder
        from aih_contexture.services.ocr_calamari import CalamariOcrService

        logger.warning("[PdfConverter] Using Calamari OCR backend")
        try:
            calamari_service = CalamariOcrService(config)
            if not calamari_service.health_check():
                logger.warning("[PdfConverter] Calamari service unavailable, falling back to Surya")
                return fallback_to_surya_ocr()
            ocr_builder = CalamariOcrBuilder(calamari_service, config=config)
            logger.info("[PdfConverter] CalamariOcrBuilder created")
            return ocr_builder
        except Exception as e:
            logger.exception("[PdfConverter] Calamari OCR init failed: %s", e)
            logger.warning("[PdfConverter] Falling back to Surya OCR")
            return fallback_to_surya_ocr()

    if ocr_backend == "paddle_ocr_v5":
        from aih_contexture.builders.paddle_ocr import PaddleOcrBuilder

        logger.warning("[PdfConverter] Using PaddleOCR PP-OCRv5 backend")
        return PaddleOcrBuilder(config=config)

    if ocr_backend == "paddleocr_vl_ocr":
        from aih_contexture.builders.paddleocr_vl_ocr import PaddleOCRVLOcrBuilder

        logger.warning("[PdfConverter] Using PaddleOCR-VL block OCR backend")
        return PaddleOCRVLOcrBuilder(config=config)

    if ocr_backend == "tesseract":
        from aih_contexture.builders.tesseract_ocr import TesseractOcrBuilder

        logger.warning("[PdfConverter] Using Tesseract OCR backend")
        return TesseractOcrBuilder(config=config)

    logger.warning("[PdfConverter] Using Surya OCR backend")
    return resolve_dependencies(ocr_builder_class)
