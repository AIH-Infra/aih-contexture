import base64
import json
import re
import time
from io import BytesIO
from typing import Annotated, Any, List, Optional

import openai
from openai import APITimeoutError, RateLimitError
from PIL import Image
from pydantic import BaseModel

from aih_contexture.logger import get_logger
from aih_contexture.schema.blocks import Block
from aih_contexture.services import BaseService

logger = get_logger()


class OpenAIService(BaseService):
    openai_base_url: Annotated[str, "Base URL for OpenAI-compatible endpoint."] = "https://api.openai.com/v1"
    openai_model: Annotated[str, "Model name."] = "gpt-4o-mini"
    openai_api_key: Annotated[str, "API key (LM Studio accepts any)."] = "lm-studio"

    openai_image_format: Annotated[str, "Image format for image_url data URLs."] = "jpeg"
    max_image_dimension: Annotated[int, "Max width/height for images sent to VLM."] = 1024
    jpeg_quality: Annotated[int, "JPEG quality (1-100)."] = 80

    # 对照实验/兼容性开关
    openai_use_stop: Annotated[bool, "Whether to include stop sequences."] = False
    vlm_response_mode: Annotated[str, "Response mode: 'text' or 'json'."] = "text"

    def __init__(self, config=None):
        if isinstance(config, dict):
            self.openai_base_url = config.get("openai_base_url", self.openai_base_url)
            self.openai_model = config.get("openai_model", self.openai_model)
            self.openai_api_key = config.get("openai_api_key") or self.openai_api_key
            self.openai_image_format = config.get("openai_image_format", self.openai_image_format)

            if config.get("max_image_dimension") is not None:
                self.max_image_dimension = int(config["max_image_dimension"])
            if config.get("jpeg_quality") is not None:
                self.jpeg_quality = int(config["jpeg_quality"])

            if config.get("timeout") is not None:
                self.timeout = int(config["timeout"])
            if config.get("max_retries") is not None:
                self.max_retries = int(config["max_retries"])
            if config.get("max_output_tokens") is not None:
                self.max_output_tokens = int(config["max_output_tokens"])

            if config.get("openai_use_stop") is not None:
                self.openai_use_stop = bool(config["openai_use_stop"])
            if config.get("vlm_response_mode") is not None:
                self.vlm_response_mode = str(config["vlm_response_mode"]).strip().lower()

        logger.info(f"[OpenAIService] Init: base_url={self.openai_base_url}, model={self.openai_model}")
        logger.info(f"[OpenAIService] Image: format={self.openai_image_format}, max_dim={self.max_image_dimension}")
        logger.info(f"[OpenAIService] Mode: vlm_response_mode={self.vlm_response_mode}, openai_use_stop={self.openai_use_stop}")

    def get_client(self) -> openai.OpenAI:
        return openai.OpenAI(
            base_url=self.openai_base_url,
            api_key=self.openai_api_key or "lm-studio",
            default_headers={
                "Cache-Control": "no-cache, no-store",
                "Pragma": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    def _resize_if_needed(self, img: Image.Image) -> Image.Image:
        w, h = img.size
        if w <= self.max_image_dimension and h <= self.max_image_dimension:
            return img
        scale = min(self.max_image_dimension / w, self.max_image_dimension / h)
        new_size = (max(1, int(w * scale)), max(1, int(h * scale)))
        return img.resize(new_size, Image.Resampling.LANCZOS)

    def _img_to_base64(self, img: Image.Image) -> str:
        fmt = (self.openai_image_format or "jpeg").lower()
        img = self._resize_if_needed(img)

        buf = BytesIO()
        if fmt in ("jpg", "jpeg"):
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            img.save(buf, format="JPEG", quality=int(self.jpeg_quality), optimize=True)
        elif fmt == "webp":
            if img.mode in ("RGBA", "P", "LA"):
                img = img.convert("RGB")
            img.save(buf, format="WEBP", quality=int(self.jpeg_quality))
        else:
            img.save(buf, format="PNG", optimize=True)

        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def process_images(self, images: List[Image.Image]) -> list:
        fmt = (self.openai_image_format or "jpeg").lower()
        mime = "jpeg" if fmt in ("jpg", "jpeg") else ("png" if fmt == "png" else "webp")
        parts = []
        for img in images:
            b64 = self._img_to_base64(img)
            parts.append({"type": "image_url", "image_url": {"url": f"data:image/{mime};base64,{b64}"}})
        return parts

    def _extract_json_any(self, text: str) -> Any:
        if not text:
            return None
        s = text.strip()

        # direct loads
        try:
            return json.loads(s)
        except Exception:
            pass

        # fenced
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", s)
        if m:
            inner = m.group(1).strip()
            try:
                return json.loads(inner)
            except Exception:
                pass

        # first list
        m = re.search(r"\[[\s\S]*\]", s)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass

        # first dict
        m = re.search(r"\{[\s\S]*\}", s)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass

        return None

    def _normalize_lines_from_any(self, data: Any) -> dict:
        def add(out: list, t: str):
            t = (t or "").strip()
            if not t:
                return
            if t in ("...", "{...}", "{ ... }", "{}", "{ }"):
                return
            out.append({"text": t})

        out: list = []

        if data is None:
            return {"lines": []}

        if isinstance(data, str):
            for ln in data.splitlines():
                add(out, ln)
            return {"lines": out}

        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    add(out, item.get("text") or item.get("line") or item.get("content"))
                elif isinstance(item, str):
                    add(out, item)
            return {"lines": out}

        if isinstance(data, dict):
            raw_lines = data.get("lines")
            if raw_lines is None:
                if "text" in data or "line" in data:
                    add(out, data.get("text") or data.get("line"))
                return {"lines": out}

            if isinstance(raw_lines, dict):
                raw_lines = [raw_lines]

            if isinstance(raw_lines, list):
                for item in raw_lines:
                    if isinstance(item, dict):
                        add(out, item.get("text") or item.get("line") or item.get("content"))
                    elif isinstance(item, str):
                        add(out, item)
            elif isinstance(raw_lines, str):
                for ln in raw_lines.splitlines():
                    add(out, ln)

            return {"lines": out}

        return {"lines": []}

    def __call__(
        self,
        prompt: str,
        image: Image.Image | List[Image.Image] | None,
        block: Block | None,
        response_schema: type[BaseModel],
        max_retries: Optional[int] = None,
        timeout: Optional[int] = None,
    ):
        """
        Returns: {"lines": [{"text": "..."} , ...]}
        - text 模式: 纯文本输出 + 更强的异常检测(循环/短语重复/回显/混乱) + 两阶段重试
        - json 模式: 解析 JSON(容错 fenced/顶层list/dict)，并做同样的异常检测
        设计目标：在“按块 VLM OCR”场景下，把坏块局部化并尽量自动修复。
        """
        # -------- configs --------
        if max_retries is None:
            max_retries = int(getattr(self, "max_retries", 2) or 2)
        if timeout is None:
            timeout = int(getattr(self, "timeout", 60) or 60)

        max_out = getattr(self, "max_output_tokens", None)
        if max_out is None:
            max_out = 2048
        max_out = int(max_out)

        mode = (self.vlm_response_mode or "text").lower().strip()
        if mode not in ("text", "json"):
            mode = "text"

        # API 级重试（超时/限流）
        api_tries_total = int(max_retries) + 1

        # 内容质量重试（可疑输出时再来一轮）
        # 这里固定 1 次：normal prompt -> hard prompt
        quality_stages = [False, True]  # hard=False/True

        # -------- helpers (local, no extra imports) --------
        def _normalize_text(s: str) -> str:
            return (s or "").replace("\r\n", "\n").replace("\r", "\n").strip()

        def _build_prompt(user_prompt: str, hard: bool) -> str:
            base = (user_prompt or "").strip()
            if not base:
                base = "Transcribe exactly as seen."

            if mode != "text":
                return base

            if hard:
                # 更短更硬：降低“规则回显/续写”概率
                return (
                    base
                    + "\n\nOnly output the text visible in the image.\n"
                    + "Keep original line breaks.\n"
                    + "If a word is unclear, output [?].\n"
                    + "Do not add any extra text.\n"
                )

            # 现有风格：约束更全，但更容易被模型“回显”
            return (
                base
                + "\n\nReturn ONLY plain text.\n"
                + "Preserve line breaks (one printed line per line).\n"
                + "Do not repeat content.\n"
                + "Do not include JSON, Markdown fences, XML/HTML tags, or commentary.\n"
            )

        def _detect_prompt_echo(text: str) -> bool:
            t = (text or "").lower()
            if not t:
                return False
            # 命中多个“规则片段”基本可判定为回显/泄露
            needles = [
                "return only plain text",
                "preserve line breaks",
                "do not repeat content",
                "do not include json",
                "markdown fences",
                "xml/html tags",
                "only output the text visible in the image",
                "if a word is unclear, output [?]",
                "stop at end of block",
            ]
            hits = 0
            for n in needles:
                if n in t:
                    hits += 1
                    if hits >= 2:
                        return True
            return False

        def _detect_html_like_garbled(text: str) -> bool:
            # 结构化残留/标签泛滥
            if not text:
                return True
            if text.count("<") >= 12 and text.count(">") >= 12:
                return True
            # 单行超长：常见于无换行循环拼接
            for ln in text.splitlines():
                if len(ln) > 650:
                    return True
            return False

        def _detect_repeat_lines(text: str) -> bool:
            lines = [ln.strip() for ln in _normalize_text(text).split("\n") if ln.strip()]
            if not lines:
                return True

            freq = {}
            for ln in lines:
                if len(ln) < 8:
                    continue
                freq[ln] = freq.get(ln, 0) + 1
                if freq[ln] >= 3:
                    return True

            # 唯一行比例过低（不再要求 >=6 行，避免漏掉少行块）
            if len(lines) >= 3:
                uniq_ratio = len(set(lines)) / max(1, len(lines))
                if uniq_ratio < 0.55:
                    return True
            return False

        def _detect_repeat_ngrams(text: str, n: int = 6, hit_threshold: int = 6) -> bool:
            """
            n-gram 重复：解决“每行不完全相同但短语循环”
            不用额外依赖，直接用 regex 分词。
            """
            t = _normalize_text(text).lower()
            if len(t) < 160:
                return False
            tokens = re.findall(r"\w+|[^\w\s]", t)
            if len(tokens) < n * 8:
                return False

            seen = {}
            hits = 0
            for i in range(0, len(tokens) - n + 1):
                gram = tuple(tokens[i : i + n])
                seen[gram] = seen.get(gram, 0) + 1
                if seen[gram] == 2:
                    hits += 1
                    if hits >= hit_threshold:
                        return True
            return False

        def _detect_repeated_segments(text: str) -> bool:
            """
            对单行/少行做片段重复检测（滑窗）
            """
            t = _normalize_text(text)
            if len(t) < 200:
                return False
            win = 64
            step = 12
            seen = {}
            for i in range(0, max(0, len(t) - win), step):
                seg = t[i : i + win]
                if len(seg.strip()) < win * 0.85:
                    continue
                seen[seg] = seen.get(seg, 0) + 1
                if seen[seg] >= 3:
                    return True
            return False

        def _is_suspicious(text: str) -> bool:
            t = _normalize_text(text)
            if not t:
                return True
            if _detect_prompt_echo(t):
                return True
            if _detect_html_like_garbled(t):
                return True
            if _detect_repeat_lines(t):
                return True
            if _detect_repeat_ngrams(t, n=6, hit_threshold=6):
                return True
            if _detect_repeated_segments(t):
                return True
            return False

        def _make_content(effective_prompt: str):
            content = []
            if image is not None:
                imgs = image if isinstance(image, list) else [image]
                content.extend(self.process_images(imgs))
            content.append({"type": "text", "text": effective_prompt})
            return content

        client = self.get_client()
        last_result = {"lines": []}

        # -------- main loop --------
        for stage_idx, hard in enumerate(quality_stages):
            effective_prompt = _build_prompt(prompt, hard=hard)
            content = _make_content(effective_prompt)

            for i in range(1, api_tries_total + 1):
                try:
                    kwargs = {
                        "model": self.openai_model,
                        "messages": [{"role": "user", "content": content}],
                        "timeout": timeout,
                        "max_tokens": max_out,
                    }

                    # stop 默认关闭；LM Studio 下 stop 包含 ``` 会导致输出为空（你已验证）[3, p.1]
                    if bool(getattr(self, "openai_use_stop", False)):
                        kwargs["stop"] = ["\nRules:", "\nSchema:", "```"]

                    resp = client.chat.completions.create(**kwargs)
                    raw_text = _normalize_text(resp.choices[0].message.content or "")

                    # 解析响应
                    if not raw_text:
                        last_result = {"lines": []}
                    elif mode == "text":
                        last_result = self._normalize_lines_from_any(raw_text)
                    else:
                        data = self._extract_json_any(raw_text)
                        if data is None:
                            last_result = {
                                "lines": [],
                                "_raw_text": raw_text,
                                "_json_parse_failed": True,
                            }
                        else:
                            # json 模式下优先保留原始结构，供上层按 response_schema / 业务契约自行解析。
                            # 不能在这里一律压平成 lines，否则会把 {corrected_pages, analysis}
                            # 这类结构化结果错误地变成 {"lines": []}。
                            last_result = data

                    # 质量判定：json 模式不做 OCR 文本型的 suspicious 检测，避免把合法/半合法 JSON 误伤。
                    if mode == "text" and _is_suspicious(raw_text):
                        logger.warning(
                            "[OpenAIService] Suspicious output; stage=%d/%d hard=%s",
                            stage_idx + 1,
                            len(quality_stages),
                            str(hard),
                        )
                        break

                    # 通过：可选去重后处理（原文件里有 _post_process_lines，但之前没接入）[3, p.1]
                    try:
                        last_result["lines"] = self._post_process_lines(last_result.get("lines") or [])
                    except Exception:
                        pass

                    return last_result

                except (APITimeoutError, RateLimitError) as e:
                    logger.warning(f"[OpenAIService] Retryable error: {e}")
                    if i < api_tries_total:
                        time.sleep(2)
                        continue
                    last_result = {"lines": []}
                except Exception as e:
                    logger.error(f"[OpenAIService] Error: {e}")
                    last_result = {"lines": []}
                    break

            # 阶段间轻微退避
            if stage_idx < len(quality_stages) - 1:
                time.sleep(0.4)

        return last_result
