from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Any

from aih_contexture.backends.capabilities import BackendCapabilities

BuilderFactory = Callable[[dict, dict[str, Any] | None], Any]


@dataclass(frozen=True, slots=True)
class LayoutBackendSpec:
    name: str
    display_name: str
    capabilities: BackendCapabilities
    # Reserved for a future factory-backed registry. The 0.5 baseline uses
    # a read-only capability catalog; builder creation remains in pipeline.py.
    builder_factory: BuilderFactory | None = None


class LayoutBackendRegistry:
    def __init__(self):
        self._specs: dict[str, LayoutBackendSpec] = {}

    def register(self, spec: LayoutBackendSpec) -> LayoutBackendSpec:
        key = self._normalize(spec.name)
        if key in self._specs:
            raise ValueError(f"Layout backend already registered: {spec.name}")
        self._specs[key] = spec
        return spec

    def get(self, name: str) -> LayoutBackendSpec:
        key = self._normalize(name)
        try:
            return self._specs[key]
        except KeyError as exc:
            available = ", ".join(self.names())
            raise ValueError(f"Unknown layout backend: {name}. Available: {available}") from exc

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


def _build_default_registry() -> LayoutBackendRegistry:
    registry = LayoutBackendRegistry()
    registry.register(
        LayoutBackendSpec(
            name="surya",
            display_name="Surya",
            capabilities=BackendCapabilities(
                name="surya",
                kind="layout",
                display_name="Surya",
                supports_bbox=True,
                supports_confidence=True,
                supports_tables=True,
                supports_formulas=True,
                notes="Current default pipeline layout backend.",
            ),
        )
    )
    registry.register(
        LayoutBackendSpec(
            name="vlm_layout",
            display_name="VLM Layout",
            capabilities=BackendCapabilities(
                name="vlm_layout",
                kind="layout",
                display_name="VLM Layout",
                requires_service=True,
                supports_bbox=True,
                supports_confidence=False,
                supports_vertical_text=True,
                supports_footnote=True,
                supports_marginalia=True,
                supports_tables=True,
                supports_formulas=True,
                notes="Existing VLM layout path; builder integration is routed through the pipeline backend factory.",
            ),
        )
    )
    registry.register(
        LayoutBackendSpec(
            name="external_layout_sidecar",
            display_name="External Layout Sidecar",
            capabilities=BackendCapabilities(
                name="external_layout_sidecar",
                kind="layout",
                display_name="External Layout Sidecar",
                supports_cpu=True,
                supports_gpu=False,
                supports_bbox=True,
                supports_confidence=True,
                supports_vertical_text=True,
                supports_footnote=True,
                supports_marginalia=True,
                supports_tables=True,
                supports_formulas=True,
                notes=(
                    "Consumes an existing MinerU/Paddle/generic layout JSON or "
                    "Contexture Middle JSON as a Pipeline layout backend. It does not "
                    "run MinerU/Paddle models directly."
                ),
            ),
        )
    )
    registry.register(
        LayoutBackendSpec(
            name="mineru_pp_doclayout_v2_direct",
            display_name="MinerU PP-DocLayoutV2 Direct",
            capabilities=BackendCapabilities(
                name="mineru_pp_doclayout_v2_direct",
                kind="layout",
                display_name="MinerU PP-DocLayoutV2 Direct",
                optional_dependency="mineru",
                supports_bbox=True,
                supports_confidence=True,
                supports_vertical_text=True,
                supports_footnote=True,
                supports_marginalia=True,
                supports_tables=True,
                supports_formulas=True,
                notes=(
                    "Optional MinerU PP-DocLayoutV2 layout-only adapter. It calls "
                    "PPDocLayoutV2LayoutModel.batch_predict directly in a MinerU sidecar Python, "
                    "without running MinerU CLI pipeline OCR/table/seal/formula stages."
                ),
            ),
        )
    )
    registry.register(
        LayoutBackendSpec(
            name="mineru_vl_layout",
            display_name="MinerU-VL Layout",
            capabilities=BackendCapabilities(
                name="mineru_vl_layout",
                kind="layout",
                display_name="MinerU-VL Layout",
                requires_service=True,
                supports_bbox=True,
                supports_confidence=False,
                supports_vertical_text=True,
                supports_footnote=True,
                supports_marginalia=True,
                supports_tables=True,
                supports_formulas=True,
                notes=(
                    "Pipeline layout-only adapter for MinerU-VL official Layout Detection. "
                    "It calls the VLM endpoint for layout boxes only; OCR remains controlled "
                    "by the selected Pipeline OCR backend."
                ),
            ),
        )
    )
    registry.register(
        LayoutBackendSpec(
            name="surya2_layout",
            display_name="Surya 2 Layout",
            capabilities=BackendCapabilities(
                name="surya2_layout",
                kind="layout",
                display_name="Surya 2 Layout",
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
                    "Pipeline layout-only adapter for Surya 2 official layout JSON. "
                    "It calls a vision-capable OpenAI-compatible service such as LM Studio "
                    "and leaves OCR to the selected Pipeline OCR backend."
                ),
            ),
        )
    )
    registry.register(
        LayoutBackendSpec(
            name="paddle_pp_doclayout_plus_l",
            display_name="Paddle PP-DocLayout Plus-L",
            capabilities=BackendCapabilities(
                name="paddle_pp_doclayout_plus_l",
                kind="layout",
                display_name="Paddle PP-DocLayout Plus-L",
                optional_dependency="paddleocr",
                supports_bbox=True,
                supports_confidence=True,
                supports_vertical_text=True,
                supports_footnote=True,
                supports_marginalia=True,
                supports_tables=True,
                supports_formulas=True,
                notes=(
                    "Optional PaddleOCR LayoutDetection adapter using PP-DocLayout_plus-L. "
                    "Runs on page images and reuses Contexture external layout normalization."
                ),
            ),
        )
    )
    registry.register(
        LayoutBackendSpec(
            name="paddle_pp_doclayout_v3",
            display_name="Paddle PP-DocLayoutV3",
            capabilities=BackendCapabilities(
                name="paddle_pp_doclayout_v3",
                kind="layout",
                display_name="Paddle PP-DocLayoutV3",
                optional_dependency="paddleocr",
                supports_bbox=True,
                supports_confidence=True,
                supports_vertical_text=True,
                supports_footnote=True,
                supports_marginalia=True,
                supports_tables=True,
                supports_formulas=True,
                notes=(
                    "Optional PaddleOCR LayoutDetection adapter using PP-DocLayoutV3. "
                    "This is the single layout detector path, not the full PP-StructureV3 document pipeline."
                ),
            ),
        )
    )
    registry.register(
        LayoutBackendSpec(
            name="humanities_layout_future",
            display_name="Future Humanities Layout Model",
            capabilities=BackendCapabilities(
                name="humanities_layout_future",
                kind="layout",
                display_name="Future Humanities Layout Model",
                implemented=False,
                supports_bbox=True,
                supports_confidence=True,
                supports_vertical_text=True,
                supports_footnote=True,
                supports_marginalia=True,
                supports_tables=True,
                supports_formulas=True,
                notes="Reserved first-party humanities layout model target.",
            ),
        )
    )
    return registry


default_layout_registry = _build_default_registry()
