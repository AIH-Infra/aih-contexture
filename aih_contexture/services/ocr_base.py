"""
OCR Service Base Class

抽象基类，定义 OCR 服务的统一接口
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
from PIL import Image
import aiohttp


class BaseOcrService(ABC):
    """OCR 服务抽象基类"""

    def __init__(self, config: dict):
        """
        初始化 OCR 服务

        Args:
            config: 配置字典
        """
        self.config = config
        self.ocr_endpoint = config.get("ocr_endpoint", "")
        self.ocr_model = config.get("ocr_model", "")
        self.ocr_api_key = config.get("ocr_api_key", "")
        self.ocr_output_format = config.get("ocr_output_format", "html")
        self.ocr_max_tokens = config.get("ocr_max_tokens", 4096)
        self.ocr_temperature = config.get("ocr_temperature", 0.0)
        self.ocr_timeout = config.get("ocr_timeout", 120)
        self.max_retries = config.get("max_retries", 3)

    @abstractmethod
    async def process_page_async(
        self,
        session: aiohttp.ClientSession,
        img: Image.Image,
        api_key: Optional[str] = None
    ) -> Any:
        """
        异步处理单页图像

        Args:
            session: aiohttp ClientSession
            img: PIL Image 对象
            api_key: API 密钥（可选，用于密钥池）

        Returns:
            OCR 输出（格式取决于具体实现）
        """
        pass

    @abstractmethod
    def get_backend_name(self) -> str:
        """
        获取后端名称

        Returns:
            后端名称字符串
        """
        pass
