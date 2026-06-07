import json
import time
import traceback
from io import BytesIO
from typing import List, Annotated
import base64

import PIL
import requests
from google import genai
from google.genai import types
from google.genai.errors import APIError
from aih_contexture.logger import get_logger
from pydantic import BaseModel

from aih_contexture.schema.blocks import Block
from aih_contexture.services import BaseService
from aih_contexture.utils.api_key_rotator import APIKeyRotator

logger = get_logger()


class BaseGeminiService(BaseService):
    gemini_model_name: Annotated[
        str, "The name of the Google model to use for the service."
    ] = "gemini-2.0-flash"
    thinking_budget: Annotated[
        int, "The thinking token budget to use for the service."
    ] = None

    def img_to_bytes(self, img: PIL.Image.Image):
        image_bytes = BytesIO()
        img.save(image_bytes, format="WEBP")
        return image_bytes.getvalue()

    def get_google_client(self, timeout: int):
        raise NotImplementedError

    def process_images(self, images):
        image_parts = [
            types.Part.from_bytes(data=self.img_to_bytes(img), mime_type="image/webp")
            for img in images
        ]
        return image_parts

    def __call__(
        self,
        prompt: str,
        image: PIL.Image.Image | List[PIL.Image.Image] | None,
        block: Block | None,
        response_schema: type[BaseModel],
        max_retries: int | None = None,
        timeout: int | None = None,
    ):
        if max_retries is None:
            max_retries = self.max_retries

        if timeout is None:
            timeout = self.timeout

        # Increase retries if multiple keys available
        if hasattr(self, 'key_rotator') and self.key_rotator.get_key_count() > 1:
            max_retries = max(max_retries, self.key_rotator.get_key_count())

        image_parts = self.format_image_for_llm(image)

        total_tries = max_retries + 1
        temperature = 0
        for tries in range(1, total_tries + 1):
            # Get current key for this attempt
            current_key = None
            if hasattr(self, 'key_rotator'):
                current_key = self.key_rotator.get_current_key()

            client = self.get_google_client(timeout=timeout, api_key=current_key)

            config = {
                "temperature": temperature,
                "response_schema": response_schema,
                "response_mime_type": "application/json",
            }
            if self.max_output_tokens:
                config["max_output_tokens"] = self.max_output_tokens

            if self.thinking_budget is not None:
                # For gemini models, we can optionally set a thinking budget in the config
                config["thinking_config"] = types.ThinkingConfig(
                    thinking_budget=self.thinking_budget
                )

            try:
                responses = client.models.generate_content(
                    model=self.gemini_model_name,
                    contents=image_parts
                    + [
                        prompt
                    ],  # According to gemini docs, it performs better if the image is the first element
                    config=config,
                )
                output = responses.candidates[0].content.parts[0].text
                total_tokens = responses.usage_metadata.total_token_count
                if block:
                    block.update_metadata(
                        llm_tokens_used=total_tokens, llm_request_count=1
                    )
                # Mark success for key rotation
                if hasattr(self, 'key_rotator'):
                    self.key_rotator.mark_success()
                return json.loads(output)
            except APIError as e:
                if e.code in [429, 443, 503]:
                    # Rate limit exceeded
                    if tries == total_tries:
                        # Last attempt failed. Give up
                        logger.error(
                            f"APIError: {e}. Max retries reached. Giving up. (Attempt {tries}/{total_tries})",
                        )
                        break
                    else:
                        # Rotate to next key on failure
                        if hasattr(self, 'key_rotator'):
                            next_key = self.key_rotator.mark_failure_and_rotate()
                            if self.key_rotator.get_key_count() > 1:
                                logger.info(f"[GoogleGeminiService] Rotating to next API key (attempt {tries+1}/{total_tries})")
                        wait_time = tries * self.retry_wait_time
                        logger.warning(
                            f"APIError: {e}. Retrying in {wait_time} seconds... (Attempt {tries}/{total_tries})",
                        )
                        time.sleep(wait_time)
                else:
                    logger.error(f"APIError: {e}")
                    # Rotate key on non-retryable errors too
                    if hasattr(self, 'key_rotator') and tries < total_tries:
                        next_key = self.key_rotator.mark_failure_and_rotate()
                        if self.key_rotator.get_key_count() > 1:
                            logger.info(f"[GoogleGeminiService] Rotating to next API key after error")
                        time.sleep(2)
                        continue
                    break
            except json.JSONDecodeError as e:
                temperature = 0.2  # Increase temperature slightly to try and get a different respons

                # The response was not valid JSON
                if tries == total_tries:
                    # Last attempt failed. Give up
                    logger.error(
                        f"JSONDecodeError: {e}. Max retries reached. Giving up. (Attempt {tries}/{total_tries})",
                    )
                    break
                else:
                    logger.warning(
                        f"JSONDecodeError: {e}. Retrying... (Attempt {tries}/{total_tries})",
                    )
            except Exception as e:
                logger.error(f"Exception: {e}")
                traceback.print_exc()
                # Rotate key on generic errors
                if hasattr(self, 'key_rotator') and tries < total_tries:
                    next_key = self.key_rotator.mark_failure_and_rotate()
                    if self.key_rotator.get_key_count() > 1:
                        logger.info(f"[GoogleGeminiService] Rotating to next API key after exception")
                    time.sleep(2)
                    continue
                break

        return {}


class GoogleGeminiService(BaseGeminiService):
    gemini_api_key: Annotated[str, "The Google API key to use for the service."] = None
    gemini_base_url: Annotated[str, "Custom base URL for Gemini API (for relay/proxy)."] = None

    def __init__(self, config=None):
        super().__init__(config)
        # Initialize API key rotator for multi-key support
        api_key = self.gemini_api_key
        base_url = self.gemini_base_url
        if isinstance(config, dict):
            api_key = config.get("gemini_api_key", api_key)
            base_url = config.get("gemini_base_url", base_url)

        self.base_url = base_url
        self.key_rotator = APIKeyRotator(api_key or "")

        if self.key_rotator.get_key_count() > 1:
            logger.info(f"[GoogleGeminiService] Using {self.key_rotator.get_key_count()} API keys with rotation")
        if self.base_url:
            logger.info(f"[GoogleGeminiService] Using custom base URL: {self.base_url}")

    def get_google_client(self, timeout: int, api_key: str = None):
        """Get Google client with optional API key override and custom base URL."""
        key = api_key if api_key is not None else self.gemini_api_key
        http_options = {"timeout": timeout * 1000}
        return genai.Client(api_key=key, http_options=http_options)

    def _call_via_http(self, prompt: str, image_parts_raw, response_schema: type[BaseModel],
                       api_key: str, timeout: int, config: dict):
        """直接 HTTP 调用中转代理（newcli 等），绕过 google-genai SDK。"""
        url = f"{self.base_url.rstrip('/')}/v1beta/models/{self.gemini_model_name}:generateContent"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

        # 构建 contents
        parts = []
        for img in (image_parts_raw or []):
            buf = BytesIO()
            img.save(buf, format="WEBP")
            parts.append({"inline_data": {"mime_type": "image/webp",
                                           "data": base64.b64encode(buf.getvalue()).decode()}})
        parts.append({"text": prompt})

        generation_config = {"temperature": config.get("temperature", 0),
                              "response_mime_type": "application/json"}
        if config.get("max_output_tokens"):
            generation_config["maxOutputTokens"] = config["max_output_tokens"]

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": generation_config,
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        total_tokens = data.get("usageMetadata", {}).get("totalTokenCount", 0)
        return json.loads(text), total_tokens

    def __call__(self, prompt, image, block, response_schema, max_retries=None, timeout=None):
        if not self.base_url:
            return super().__call__(prompt, image, block, response_schema, max_retries, timeout)

        if max_retries is None:
            max_retries = self.max_retries
        if timeout is None:
            timeout = self.timeout
        if hasattr(self, 'key_rotator') and self.key_rotator.get_key_count() > 1:
            max_retries = max(max_retries, self.key_rotator.get_key_count())

        # 原始图片列表（PIL），传给 _call_via_http 自行编码
        images = image if isinstance(image, list) else ([image] if image else [])

        total_tries = max_retries + 1
        temperature = 0
        for tries in range(1, total_tries + 1):
            current_key = self.key_rotator.get_current_key() if hasattr(self, 'key_rotator') else self.gemini_api_key
            config = {"temperature": temperature, "max_output_tokens": self.max_output_tokens}
            try:
                result, total_tokens = self._call_via_http(prompt, images, response_schema, current_key, timeout, config)
                if block:
                    block.update_metadata(llm_tokens_used=total_tokens, llm_request_count=1)
                if hasattr(self, 'key_rotator'):
                    self.key_rotator.mark_success()
                return result
            except requests.HTTPError as e:
                status = e.response.status_code if e.response is not None else 0
                logger.error(f"[GoogleGeminiService] HTTP {status}: {e}")
                if status in [429, 503] and tries < total_tries:
                    if hasattr(self, 'key_rotator'):
                        self.key_rotator.mark_failure_and_rotate()
                    time.sleep(tries * self.retry_wait_time)
                    continue
                break
            except (json.JSONDecodeError, KeyError) as e:
                temperature = 0.2
                if tries < total_tries:
                    logger.warning(f"[GoogleGeminiService] Parse error: {e}, retrying...")
                    continue
                break
            except Exception as e:
                logger.error(f"[GoogleGeminiService] Exception: {e}")
                traceback.print_exc()
                if hasattr(self, 'key_rotator') and tries < total_tries:
                    self.key_rotator.mark_failure_and_rotate()
                    time.sleep(2)
                    continue
                break
        return {}
