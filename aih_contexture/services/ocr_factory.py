"""
OCR Service Factory

工厂类，根据配置创建对应的 OCR 服务实例
"""

from typing import Optional
from aih_contexture.services.ocr_base import BaseOcrService
from aih_contexture.logger import get_logger

logger = get_logger()


class OcrServiceFactory:
    """OCR 服务工厂"""

    @staticmethod
    def create_service(config: dict) -> BaseOcrService:
        """
        根据配置创建 OCR 服务实例

        Args:
            config: 配置字典，必须包含 ocr_backend 字段

        Returns:
            BaseOcrService 实例

        Raises:
            ValueError: 不支持的后端类型
        """
        backend = config.get("ocr_backend", "chandra")

        if backend == "chandra":
            from aih_contexture.services.ocr_chandra import OcrChandraService
            logger.info("Creating Chandra OCR service")
            return OcrChandraService(config)
        elif backend == "churro":
            from aih_contexture.services.ocr_churro import OcrChurroService
            logger.info("Creating Churro OCR service")
            return OcrChurroService(config)
        elif backend in {"paddleocr_vl", "paddleocr_vl_ocr"}:
            from aih_contexture.services.ocr_vlm_specialized import OcrPaddleOCRVLService
            logger.info("Creating PaddleOCR-VL specialized service")
            service_config = dict(config)
            if backend == "paddleocr_vl_ocr":
                service_config.setdefault("paddleocr_vl_backend_name", "paddleocr_vl_ocr")
            return OcrPaddleOCRVLService(service_config)
        elif backend == "mineru_vl":
            from aih_contexture.services.ocr_vlm_specialized import OcrMinerUVLService
            logger.info("Creating MinerU-VL specialized service")
            return OcrMinerUVLService(config)
        elif backend in {"surya2", "surya2_ocr"}:
            from aih_contexture.services.ocr_vlm_specialized import OcrSurya2Service
            logger.info("Creating Surya 2 specialized service")
            return OcrSurya2Service(config)
        else:
            raise ValueError(f"Unsupported OCR backend: {backend}")
