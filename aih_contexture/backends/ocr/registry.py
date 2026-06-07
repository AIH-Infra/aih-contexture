from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any

from aih_contexture.backends.capabilities import BackendCapabilities

BuilderFactory = Callable[[dict, dict[str, Any] | None], Any]


@dataclass(frozen=True, slots=True)
class OcrBackendSpec:
    name: str
    display_name: str
    capabilities: BackendCapabilities
    # Reserved for a future factory-backed registry. The 0.5 baseline uses
    # a read-only capability catalog; builder creation remains in pipeline.py.
    builder_factory: BuilderFactory | None = None


class OcrBackendRegistry:
    def __init__(self):
        self._specs: dict[str, OcrBackendSpec] = {}

    def register(self, spec: OcrBackendSpec) -> OcrBackendSpec:
        key = self._normalize(spec.name)
        if key in self._specs:
            raise ValueError(f"OCR backend already registered: {spec.name}")
        self._specs[key] = spec
        return spec

    def get(self, name: str) -> OcrBackendSpec:
        key = self._normalize(name)
        try:
            return self._specs[key]
        except KeyError as exc:
            available = ", ".join(self.names())
            raise ValueError(f"Unknown OCR backend: {name}. Available: {available}") from exc

    def names(self, implemented_only: bool = True) -> list[str]:
        specs = self._specs.values()
        if implemented_only:
            specs = [spec for spec in specs if spec.capabilities.implemented]
        return sorted(spec.name for spec in specs)

    def capabilities(self, name: str) -> BackendCapabilities:
        return self.get(name).capabilities

    @staticmethod
    def _normalize(name: str) -> str:
        return name.strip().lower().replace("-", "_")


def _build_default_registry() -> OcrBackendRegistry:
    registry = OcrBackendRegistry()
    registry.register(
        OcrBackendSpec(
            name="surya",
            display_name="Surya OCR",
            capabilities=BackendCapabilities(
                name="surya",
                kind="ocr",
                display_name="Surya OCR",
                supports_bbox=True,
                supports_confidence=True,
                languages=("multi",),
                notes="Current default pipeline OCR backend.",
            ),
        )
    )
    registry.register(
        OcrBackendSpec(
            name="vlm_ocr",
            display_name="VLM OCR",
            capabilities=BackendCapabilities(
                name="vlm_ocr",
                kind="ocr",
                display_name="VLM OCR",
                requires_service=True,
                supports_bbox=False,
                supports_confidence=False,
                supports_vertical_text=True,
                supports_footnote=True,
                supports_marginalia=True,
                languages=("multi",),
                notes="Existing VLM OCR path; service integration remains in the pipeline factory.",
            ),
        )
    )
    registry.register(
        OcrBackendSpec(
            name="calamari",
            display_name="Calamari OCR",
            capabilities=BackendCapabilities(
                name="calamari",
                kind="ocr",
                display_name="Calamari OCR",
                requires_service=True,
                supports_bbox=True,
                supports_confidence=True,
                languages=("historical-european",),
                notes="Service-backed OCR path for historical European print.",
            ),
        )
    )
    registry.register(
        OcrBackendSpec(
            name="paddle_ocr_v5",
            display_name="PaddleOCR PP-OCRv5",
            capabilities=BackendCapabilities(
                name="paddle_ocr_v5",
                kind="ocr",
                display_name="PaddleOCR PP-OCRv5",
                optional_dependency="paddleocr",
                supports_bbox=True,
                supports_confidence=True,
                supports_vertical_text=True,
                languages=("multi", "cjk"),
                notes="Optional PaddleOCR PP-OCRv5 adapter. Writes recognized text back into Pipeline line/span structures.",
            ),
        )
    )
    registry.register(
        OcrBackendSpec(
            name="paddleocr_vl_ocr",
            display_name="PaddleOCR-VL OCR",
            capabilities=BackendCapabilities(
                name="paddleocr_vl_ocr",
                kind="ocr",
                display_name="PaddleOCR-VL OCR",
                requires_service=True,
                optional_dependency="paddleocr-vl-service",
                supports_bbox=True,
                supports_confidence=False,
                supports_vertical_text=True,
                supports_footnote=True,
                supports_tables=True,
                supports_formulas=True,
                languages=("multi", "cjk"),
                notes=(
                    "Pipeline OCR adapter that uses PaddleOCR-VL VLRecognition on existing "
                    "layout block crops. It does not run a second layout pass."
                ),
            ),
        )
    )
    registry.register(
        OcrBackendSpec(
            name="tesseract",
            display_name="Tesseract OCR",
            capabilities=BackendCapabilities(
                name="tesseract",
                kind="ocr",
                display_name="Tesseract OCR",
                optional_dependency="tesseract",
                supports_cpu=True,
                supports_gpu=False,
                supports_bbox=True,
                supports_confidence=True,
                languages=("multi",),
                notes=(
                    "Optional CPU OCR backend using a system Tesseract executable. "
                    "It writes recognized line text back into Contexture spans before Markdown rendering."
                ),
            ),
        )
    )
    registry.register(
        OcrBackendSpec(
            name="mineru_pytorch_paddle_ocr",
            display_name="MinerU PyTorch/Paddle OCR",
            capabilities=BackendCapabilities(
                name="mineru_pytorch_paddle_ocr",
                kind="ocr",
                display_name="MinerU PyTorch/Paddle OCR",
                implemented=False,
                optional_dependency="mineru",
                supports_bbox=True,
                supports_confidence=True,
                supports_vertical_text=True,
                languages=("multi", "cjk"),
                notes="Planned optional adapter. Must emit verifiable spans before Markdown rendering.",
            ),
        )
    )
    return registry


default_ocr_registry = _build_default_registry()
