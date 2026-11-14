"""Model resources for the optional native Paddle OCR Torch backend.

No runtime or weights are loaded while discovering paths. Existing model
caches can be reused; downloads only happen when explicitly requested.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from aih_contexture.backends.external_config import default_runtime_root, _mineru_pipeline_model_roots

RESOURCE_DIR = Path(__file__).with_name("resources")
MODEL_SUBPATH = Path("models/OCR/paddleocr_torch")
VERSIONS = ("PP-OCRv5", "PP-OCRv6")

# Pin public snapshots so an explicit download cannot silently change weights
# when the upstream repositories are updated.
_V6_REPOSITORIES = {
    "ch_PP-OCRv6_small_det_infer.safetensors": (
        "PaddlePaddle/PP-OCRv6_small_det_safetensors",
        "eae2ee920a39fb3087637d3dbb58df1896ec1f24",
    ),
    "ch_PP-OCRv6_small_rec_infer.safetensors": (
        "PaddlePaddle/PP-OCRv6_small_rec_safetensors",
        "fe049fb103f57443fe8840c54ed06b702f3c1de5",
    ),
    "ch_PP-OCRv6_medium_rec_infer.safetensors": (
        "PaddlePaddle/PP-OCRv6_medium_rec_safetensors",
        "024cad6a831de75c2c3c26e711ba8c4a82ccd24b",
    ),
}


def model_spec(lang: str = "ch", version: str = "PP-OCRv5") -> dict[str, str]:
    if version not in VERSIONS:
        raise ValueError(f"Unsupported Paddle OCR Torch version: {version!r}. Choose {VERSIONS}.")
    config_path = RESOURCE_DIR / f"paddle_torch_models_{version[-2:]}.yml"
    languages = yaml.safe_load(config_path.read_text(encoding="utf-8"))["lang"]
    aliases = {"japan": "ch_server", "chinese_cht": "ch_server", "en": "ch", "latin": "ch"}
    resolved = lang if lang in languages else aliases.get(lang, lang)
    if resolved not in languages:
        raise ValueError(f"Unsupported language {lang!r} for {version}. Available: {', '.join(languages)}")
    return dict(languages[resolved])


def default_model_dir() -> Path:
    return default_runtime_root() / "contexture/data/shared" / MODEL_SUBPATH


def resolve_model_dir(config: dict[str, Any] | None = None, *, download: bool = False) -> Path:
    config = config or {}
    allow_download = config.get("mineru_ocr_allow_download", False)
    if not isinstance(allow_download, bool):
        raise ValueError("mineru_ocr_allow_download must be a boolean (true or false).")
    spec = model_spec(str(config.get("mineru_ocr_lang") or config.get("paddle_ocr_lang") or "ch"), str(config.get("mineru_ocr_version") or "PP-OCRv5"))
    required = (spec["det"], spec["rec"])
    configured = config.get("mineru_ocr_model_dir") or os.environ.get("CONTEXTURE_PADDLE_TORCH_MODEL_DIR")
    if configured:
        candidates = [Path(configured).expanduser().resolve()]
    else:
        candidates = [default_model_dir(), *(root / MODEL_SUBPATH for root in _mineru_pipeline_model_roots())]
    for candidate in candidates:
        if all((candidate / name).is_file() for name in required):
            return candidate
    target = candidates[0]
    if download and allow_download:
        from huggingface_hub import hf_hub_download
        from filelock import FileLock

        target.mkdir(parents=True, exist_ok=True)
        # Parallel page/file workers may reach a missing model simultaneously.
        with FileLock(target / ".download.lock"):
            for name in dict.fromkeys(required):
                if (target / name).is_file():
                    continue
                if name in _V6_REPOSITORIES:
                    repo_id, revision = _V6_REPOSITORIES[name]
                    filename = "model.safetensors"
                else:
                    repo_id, revision = "OpenDataLab/PDF-Extract-Kit-1.0", None
                    filename = f"{MODEL_SUBPATH.as_posix()}/{name}"
                downloaded = hf_hub_download(
                    repo_id=repo_id,
                    filename=filename,
                    local_dir=target / ".download",
                    **({"revision": revision} if revision else {}),
                )
                # The hub download is already complete and atomic. Publish it
                # under our model filename without retaining a second copy.
                Path(downloaded).replace(target / name)
        if all((target / name).is_file() for name in required):
            return target
    missing = [name for name in required if not (target / name).is_file()]
    raise FileNotFoundError(
        f"Paddle OCR Torch weights missing in {target}: {', '.join(missing)}. "
        "Set mineru_ocr_model_dir to a folder containing the selected weights, "
        "or explicitly enable mineru_ocr_allow_download."
    )
