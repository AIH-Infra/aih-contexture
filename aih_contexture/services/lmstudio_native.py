import json
import time
from typing import Annotated, List

import PIL
import requests
from PIL import Image
from pydantic import BaseModel

from aih_contexture.logger import get_logger
from aih_contexture.schema.blocks import Block
from aih_contexture.services import BaseService

logger = get_logger()


class LMStudioNativeService(BaseService):
    lmstudio_base_url: Annotated[
        str, "LM Studio native endpoint. Defaults to /api/v1/chat."
    ] = "http://localhost:1234/api/v1/chat"
    lmstudio_model: Annotated[str, "The model name to use for LM Studio native API."] = "local-model"
    lmstudio_api_key: Annotated[str, "API key (LM Studio accepts any value)."] = "lm-studio"
    lmstudio_thinking_mode: Annotated[
        str, "Thinking mode for LM Studio native API: off or on."
    ] = "off"
    lmstudio_temperature: Annotated[float, "Sampling temperature for LM Studio native API."] = 0.0

    def process_images(self, images: List[Image.Image]) -> list:
        if isinstance(images, Image.Image):
            images = [images]

        return [
            {
                "type": "image",
                "data_url": f"data:image/webp;base64,{self.img_to_base64(img)}",
            }
            for img in images
        ]

    def _normalize_url(self) -> str:
        base_url = (self.lmstudio_base_url or "").strip().rstrip("/")
        if not base_url:
            return "http://localhost:1234/api/v1/chat"
        if base_url.endswith("/v1"):
            return f"{base_url[:-3]}/api/v1/chat"
        return base_url

    def _build_prompt(self, prompt: str, response_schema: type[BaseModel]) -> str:
        schema_json = json.dumps(
            response_schema.model_json_schema(), ensure_ascii=False, indent=2
        )
        if self.lmstudio_thinking_mode == "on":
            thinking_line = (
                "You may reason internally if useful, but do not expose your reasoning."
            )
        else:
            thinking_line = (
                "Do not output chain-of-thought, reasoning, or commentary."
            )

        return (
            f"{(prompt or '').strip()}\n\n"
            f"You must return valid JSON matching this schema:\n{schema_json}\n\n"
            f"{thinking_line}\n"
            "Respond with JSON only. Do not include markdown fences."
        ).strip()

    def _build_payload(
        self,
        prompt: str,
        image_parts: list,
        include_reasoning_field: bool,
    ) -> dict:
        payload = {
            "model": self.lmstudio_model,
            "input": [*image_parts, {"type": "text", "content": prompt}],
            "temperature": self.lmstudio_temperature,
            "max_output_tokens": int(self.max_output_tokens or 4096),
        }

        # Some LM Studio native builds may accept a reasoning hint.
        # We treat this as best-effort and will retry without it if rejected.
        if include_reasoning_field and self.lmstudio_thinking_mode == "on":
            payload["reasoning"] = {"effort": "medium"}

        return payload

    def _extract_response_text(self, body: dict) -> str:
        candidates = [
            body.get("content"),
            body.get("output_text"),
            body.get("text"),
            body.get("response"),
        ]
        for item in candidates:
            if isinstance(item, str) and item.strip():
                return item.strip()

        output = body.get("output")
        if isinstance(output, list):
            preferred = []
            fallback = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                bucket = preferred if item.get("type") in {"text", "content", "message"} else fallback
                for key in ("text", "content"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        bucket.append(value)
                content = item.get("content")
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict):
                            value = part.get("text")
                            if isinstance(value, str) and value.strip():
                                bucket.append(value)
            if preferred:
                return "".join(preferred).strip()
            if fallback:
                return "".join(fallback).strip()

        prediction = body.get("prediction")
        if isinstance(prediction, dict):
            for key in ("text", "content"):
                value = prediction.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        choices = body.get("choices")
        if isinstance(choices, list) and choices:
            message = choices[0].get("message", {})
            for key in ("content", "reasoning_content"):
                value = message.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return ""

    def _parse_schema_response(
        self, response_text: str, response_schema: type[BaseModel]
    ) -> dict | None:
        if not response_text:
            return None

        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:].strip()
        if text.startswith("```"):
            text = text[3:].strip()
        if text.endswith("```"):
            text = text[:-3].strip()

        candidates = [text]
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidates.append(text[start : end + 1])

        for candidate in candidates:
            try:
                return response_schema.model_validate_json(candidate).model_dump()
            except Exception:
                continue

        return None

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

        total_tries = max_retries + 1
        url = self._normalize_url()
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.lmstudio_api_key or 'lm-studio'}",
        }
        image_parts = self.format_image_for_llm(image)
        prompt_text = self._build_prompt(prompt, response_schema)
        allow_reasoning_field = self.lmstudio_thinking_mode == "on"

        for tries in range(1, total_tries + 1):
            try:
                payload = self._build_payload(
                    prompt_text,
                    image_parts,
                    include_reasoning_field=allow_reasoning_field,
                )
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=timeout,
                )

                if response.status_code >= 400:
                    if allow_reasoning_field and response.status_code in {400, 404, 422}:
                        logger.warning(
                            "[LMStudioNativeService] Native reasoning field rejected; retrying without it."
                        )
                        allow_reasoning_field = False
                        time.sleep(0.5)
                        continue
                    response.raise_for_status()

                body = response.json()
                response_text = self._extract_response_text(body)
                parsed = self._parse_schema_response(response_text, response_schema)
                if parsed is not None:
                    usage = body.get("usage") or {}
                    total_tokens = usage.get("total_tokens")
                    if block and isinstance(total_tokens, int):
                        block.update_metadata(
                            llm_tokens_used=total_tokens,
                            llm_request_count=1,
                        )
                    return parsed

                logger.warning(
                    "[LMStudioNativeService] Failed to parse model response as schema JSON."
                )
            except requests.RequestException as e:
                if tries == total_tries:
                    logger.error(
                        f"[LMStudioNativeService] Request failed after retries: {e}"
                    )
                    break
                wait_time = tries * self.retry_wait_time
                logger.warning(
                    f"[LMStudioNativeService] Request error: {e}. Retrying in {wait_time} seconds..."
                )
                time.sleep(wait_time)
            except Exception as e:
                logger.error(f"[LMStudioNativeService] Inference failed: {e}")
                break

        return {}
