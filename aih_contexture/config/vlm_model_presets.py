from __future__ import annotations

from typing import Any


VLM_SPECIALIZED_BACKEND_LABELS: dict[str, str] = {
    "chandra": "Chandra OCR - 通用文档模型（Datalab）",
    "churro": "Churro OCR - 历史文档专用模型（3B 参数）",
    "chrome_screenai": "Chrome ScreenAI - 本地原生 OCR",
    "paddleocr_vl": "PaddleOCR-VL - 文档解析 VLM/Pipeline",
    "mineru_vl": "MinerU-VL - 文档理解 VLM",
    "surya2": "Surya 2 - 轻量文档 VLM",
}


VLM_SPECIALIZED_MODEL_PRESETS: dict[str, dict[str, Any]] = {
    "chandra": {
        "default_version": "2.0",
        "default_quant": "q8_0",
        "versions": {
            "1.0": {
                "label": "Chandra 1.0",
                "family": "Chandra OCR 1.0",
                "models": {
                    "bf16": "chandra-ocr@bf16",
                    "f16": "chandra-ocr@f16",
                    "q8_0": "chandra-ocr@q8_0",
                    "q6_k": "chandra-ocr@q6_k",
                },
            },
            "2.0": {
                "label": "Chandra 2.0",
                "family": "Chandra OCR 2.0",
                "models": {
                    "bf16": "chandra-ocr-2@bf16",
                    "f16": "chandra-ocr-2@f16",
                    "q8_0": "chandra-ocr-2@q8_0",
                    "q6_k": "chandra-ocr-2@q6_k",
                },
            },
        },
    },
    "churro": {
        "default_version": "3b",
        "default_quant": "q8_0",
        "versions": {
            "3b": {
                "label": "Churro 3B",
                "family": "Churro OCR 3B",
                "models": {
                    "f16": "churro-3b@f16",
                    "q8_0": "churro-3b@q8_0",
                    "q6_k": "churro-3b@q6_k",
                },
            },
        },
    },
    "chrome_screenai": {
        "default_version": "native",
        "versions": {
            "native": {
                "label": "Chrome ScreenAI（本地）",
                "family": "Chrome ScreenAI Local",
                "model": "chrome-screenai-local",
            },
        },
    },
    "paddleocr_vl": {
        "default_version": "1.5",
        "versions": {
            "1.6": {
                "label": "PaddleOCR-VL 1.6",
                "family": "PaddleOCR-VL 1.6",
                "model": "paddleocr-vl-1.6",
            },
            "1.5": {
                "label": "PaddleOCR-VL 1.5",
                "family": "PaddleOCR-VL 1.5",
                "model": "paddleocr-vl-1.5",
            },
        },
    },
    "mineru_vl": {
        "default_version": "2.5pro-2605",
        "default_quant": "f16",
        "versions": {
            "2.5pro-2605": {
                "label": "MinerU-VL 2.5 Pro 2605 1.2B",
                "family": "MinerU-VL 2.5 Pro 2605 1.2B",
                "models": {
                    "f16": "mineru2.5-pro-2605-1.2b@f16",
                    "q8_0": "mineru2.5-pro-2605-1.2b@q8_0",
                },
            },
            "2.5pro-2604": {
                "label": "MinerU-VL 2.5 Pro 2604 1.2B",
                "family": "MinerU-VL 2.5 Pro 2604 1.2B",
                "models": {
                    "f16": "mineru2.5-pro-2604-1.2b@f16",
                    "q8_0": "mineru2.5-pro-2604-1.2b@q8_0",
                },
            },
        },
    },
    "surya2": {
        "default_version": "2.0",
        "versions": {
            "2.0": {
                "label": "Surya 2",
                "family": "Surya OCR 2",
                "model": "surya-ocr-2-lmstudio",
            },
        },
    },
}


def backend_label(backend: str) -> str:
    return VLM_SPECIALIZED_BACKEND_LABELS.get(backend, backend)


def _backend_preset(backend: str) -> dict[str, Any]:
    return VLM_SPECIALIZED_MODEL_PRESETS.get(backend, VLM_SPECIALIZED_MODEL_PRESETS["chandra"])


def default_version(backend: str) -> str:
    preset = _backend_preset(backend)
    return str(preset["default_version"])


def default_quant(backend: str) -> str | None:
    preset = _backend_preset(backend)
    value = preset.get("default_quant")
    return str(value) if value is not None else None


def normalize_version(backend: str, version: str | None = None) -> str:
    preset = _backend_preset(backend)
    selected = version or preset["default_version"]
    if selected not in preset["versions"]:
        selected = preset["default_version"]
    return str(selected)


def normalize_quant(backend: str, version: str | None = None, quant: str | None = None) -> str | None:
    options = quant_options(backend, normalize_version(backend, version))
    if not options:
        return None
    selected = quant or default_quant(backend)
    if selected not in options:
        selected = default_quant(backend)
    if selected not in options:
        selected = options[0]
    return str(selected)


def version_options(backend: str) -> list[str]:
    return list(_backend_preset(backend)["versions"].keys())


def quant_options(backend: str, version: str | None = None) -> list[str]:
    version_preset = version_preset_for(backend, version)
    models = version_preset.get("models")
    if not isinstance(models, dict):
        return []
    return list(models.keys())


def version_label(backend: str, version: str | None = None) -> str:
    version_preset = version_preset_for(backend, version)
    return str(version_preset.get("label") or version or default_version(backend))


def version_preset_for(backend: str, version: str | None = None) -> dict[str, Any]:
    preset = _backend_preset(backend)
    versions = preset["versions"]
    selected = normalize_version(backend, version)
    return versions[selected]


def resolve_vlm_model(
    backend: str,
    *,
    version: str | None = None,
    quant: str | None = None,
    override: str | None = None,
) -> str:
    if override and override.strip():
        return override.strip()

    preset = _backend_preset(backend)
    selected_version = normalize_version(backend, version)
    version_preset = preset["versions"][selected_version]

    if "model" in version_preset:
        return str(version_preset["model"])

    models = version_preset["models"]
    selected_quant = normalize_quant(backend, selected_version, quant)
    return str(models[selected_quant])


def model_family_label(backend: str, version: str | None = None) -> str:
    version_preset = version_preset_for(backend, version)
    return str(version_preset.get("family") or version_preset.get("label") or backend)
