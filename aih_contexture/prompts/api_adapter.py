"""
API Parameter Adapter for cross-API compatibility.

Handles parameter differences between different VLM APIs:
- OpenAI (GPT-4V, GPT-4o)
- Google Gemini
- Alibaba Qwen
- Anthropic Claude
"""

from aih_contexture.logger import get_logger

logger = get_logger()


class APIParameterAdapter:
    """API 参数适配器，处理不同 API 的参数差异"""

    # API 支持的参数映射
    SUPPORTED_PARAMS = {
        "openai": [
            "temperature", "top_p", "max_tokens",
            "presence_penalty", "frequency_penalty", "seed"
        ],
        "gemini": ["temperature", "top_p", "top_k", "max_tokens"],
        "qwen": ["temperature", "top_p", "top_k", "max_tokens"],
        "claude": ["temperature", "top_p", "top_k", "max_tokens"],
        "unknown": ["temperature", "top_p", "max_tokens"]  # 最小公共集
    }

    @staticmethod
    def detect_api_type(base_url: str, model: str) -> str:
        """
        根据 base_url 和 model 自动检测 API 类型

        Args:
            base_url: API base URL
            model: 模型名称

        Returns:
            "openai" | "gemini" | "qwen" | "claude" | "unknown"
        """
        base_url_lower = base_url.lower()
        model_lower = model.lower()

        # 优先检测 URL 格式（比模型名称更可靠）
        # OpenAI 兼容格式通常以 /v1 结尾
        if base_url_lower.endswith('/v1') or '/v1/' in base_url_lower:
            # 这是 OpenAI 兼容格式的中转服务
            if "qwen" in model_lower:
                return "qwen"
            return "openai"

        if "openai.com" in base_url_lower or "gpt" in model_lower:
            return "openai"
        elif "generativelanguage.googleapis.com" in base_url_lower or "gemini" in model_lower:
            return "gemini"
        elif "dashscope.aliyuncs.com" in base_url_lower or "qwen" in model_lower:
            return "qwen"
        elif "anthropic.com" in base_url_lower or "claude" in model_lower:
            return "claude"
        else:
            logger.warning(f"Unknown API type for base_url={base_url}, model={model}, using minimal parameter set")
            return "unknown"

    @staticmethod
    def adapt_params(api_type: str, params: dict) -> dict:
        """
        根据 API 类型过滤和转换参数

        Args:
            api_type: "openai", "gemini", "qwen", "claude", "unknown"
            params: 原始参数字典

        Returns:
            适配后的参数字典
        """
        supported = APIParameterAdapter.SUPPORTED_PARAMS.get(api_type, [])
        adapted = {k: v for k, v in params.items() if k in supported}

        # 记录被过滤的参数
        filtered = set(params.keys()) - set(adapted.keys())
        if filtered:
            logger.info(f"[APIParameterAdapter] Filtered unsupported params for {api_type}: {filtered}")

        return adapted
