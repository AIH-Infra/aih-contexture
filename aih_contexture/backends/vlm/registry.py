from __future__ import annotations

from dataclasses import dataclass

from aih_contexture.backends.capabilities import BackendCapabilities


@dataclass(frozen=True, slots=True)
class VlmBackendSpec:
    name: str
    display_name: str
    capabilities: BackendCapabilities


class VlmBackendRegistry:
    def __init__(self):
        self._specs: dict[str, VlmBackendSpec] = {}

    def register(self, spec: VlmBackendSpec) -> VlmBackendSpec:
        key = self._normalize(spec.name)
        if key in self._specs:
            raise ValueError(f"VLM backend already registered: {spec.name}")
        self._specs[key] = spec
        return spec

    def get(self, name: str) -> VlmBackendSpec:
        key = self._normalize(name)
        try:
            return self._specs[key]
        except KeyError as exc:
            available = ", ".join(self.names())
            raise ValueError(f"Unknown VLM backend: {name}. Available: {available}") from exc

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


def _build_default_registry() -> VlmBackendRegistry:
    registry = VlmBackendRegistry()
    registry.register(
        VlmBackendSpec(
            name="vlm_generalized",
            display_name="Generalized VLM",
            capabilities=BackendCapabilities(
                name="vlm_generalized",
                kind="vlm",
                display_name="Generalized VLM",
                requires_service=True,
                supports_bbox=False,
                supports_confidence=False,
                supports_vertical_text=True,
                supports_footnote=True,
                supports_marginalia=True,
                supports_tables=True,
                supports_formulas=True,
                languages=("multi",),
                notes=(
                    "Existing generalized page-image VLM mode. It uses configurable "
                    "OpenAI-compatible or provider-specific services and then maps "
                    "structured output into Contexture Middle when requested."
                ),
            ),
        )
    )
    registry.register(
        VlmBackendSpec(
            name="chandra",
            display_name="Chandra",
            capabilities=BackendCapabilities(
                name="chandra",
                kind="vlm",
                display_name="Chandra",
                requires_service=True,
                supports_bbox=True,
                supports_confidence=False,
                supports_vertical_text=True,
                supports_footnote=True,
                supports_marginalia=True,
                supports_tables=True,
                supports_formulas=True,
                languages=("multi",),
                notes=(
                    "Existing specialized OCR/document VLM path. It should keep "
                    "the upstream Chandra prompt and output protocol, then adapt "
                    "official outputs into Contexture Middle."
                ),
            ),
        )
    )
    registry.register(
        VlmBackendSpec(
            name="churro",
            display_name="Churro",
            capabilities=BackendCapabilities(
                name="churro",
                kind="vlm",
                display_name="Churro",
                requires_service=True,
                supports_bbox=True,
                supports_confidence=False,
                supports_vertical_text=True,
                supports_footnote=True,
                supports_marginalia=True,
                supports_tables=True,
                supports_formulas=True,
                languages=("multi",),
                notes=(
                    "Existing specialized OCR/document VLM path. It should keep "
                    "the upstream XML protocol and adapt official outputs into "
                    "Contexture Middle."
                ),
            ),
        )
    )
    registry.register(
        VlmBackendSpec(
            name="paddleocr_vl",
            display_name="PaddleOCR-VL",
            capabilities=BackendCapabilities(
                name="paddleocr_vl",
                kind="vlm",
                display_name="PaddleOCR-VL",
                requires_service=True,
                optional_dependency="paddleocr-vl",
                supports_bbox=True,
                supports_confidence=True,
                supports_vertical_text=True,
                supports_footnote=True,
                supports_marginalia=True,
                supports_tables=True,
                supports_formulas=True,
                languages=("multi", "cjk"),
                notes=(
                    "Implemented VLM specialized backend for the PaddleOCR-VL "
                    "model family, with internal version profiles such as 1.5 "
                    "and 1.6. "
                    "The official Paddle pipeline combines PP-DocLayoutV3 "
                    "layout detection with VLRecognition block prompts; "
                    "OpenAI-compatible model mounts use the upstream "
                    "VLRecognition prompt protocol such as OCR, Table "
                    "Recognition, Chart Recognition, Formula Recognition, Seal "
                    "Recognition, and Spotting. A Paddle /layout-parsing "
                    "service should be treated as the full pipeline mode when "
                    "present. Preserve raw prompt output and block metadata "
                    "before adapting to Contexture Middle."
                ),
            ),
        )
    )
    registry.register(
        VlmBackendSpec(
            name="mineru_vl",
            display_name="MinerU-VL",
            capabilities=BackendCapabilities(
                name="mineru_vl",
                kind="vlm",
                display_name="MinerU-VL",
                requires_service=True,
                optional_dependency="mineru-vl",
                supports_bbox=True,
                supports_confidence=True,
                supports_vertical_text=True,
                supports_footnote=True,
                supports_marginalia=True,
                supports_tables=True,
                supports_formulas=True,
                languages=("multi", "cjk"),
                notes=(
                    "Implemented VLM specialized backend for the end-to-end "
                    "MinerU-VL model family, with internal version profiles "
                    "such as 2.5pro-2604 and 2.5pro-2605. This is the "
                    "default structured OpenAI-compatible path: first call the "
                    "upstream Layout Detection prompt, then run MinerU block "
                    "recognition prompts on cropped regions. Preserve raw "
                    "MinerU output and normalize official protocol text before "
                    "adapting to Contexture Middle. "
                    "Structured MinerU JSON or middle_json from sidecar/native "
                    "runtimes can still be imported after the fact. Do not mix "
                    "this with the MinerU PP-DocLayoutV2 layout sidecar. "
                    "Contexture exposes a single official-compatible structured "
                    "MinerU-VL path; page-level text fallback is not a product "
                    "mode because it cannot preserve block labels and geometry."
                ),
            ),
        )
    )
    return registry


default_vlm_registry = _build_default_registry()
