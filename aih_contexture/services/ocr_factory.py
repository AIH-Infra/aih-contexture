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
        else:
            raise ValueError(f"Unsupported OCR backend: {backend}")
