from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from aih_contexture.backends.layout.paddle_runtime import PaddleLayoutDetectionRuntime
from aih_contexture.builders.external_layout_sidecar import ExternalLayoutSidecarBuilder
from aih_contexture.providers.pdf import PdfProvider
from aih_contexture.schema.document import Document


class PaddleLayoutDetectionBuilder(ExternalLayoutSidecarBuilder):
    """Pipeline layout builder backed by PaddleOCR LayoutDetection."""

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        runtime: PaddleLayoutDetectionRuntime | None = None,
    ):
        config = dict(config or {})
        layout_backend = str(config.get("layout_backend") or "paddle_pp_doclayout_plus_l")
        default_model = "PP-DocLayoutV3" if layout_backend == "paddle_pp_doclayout_v3" else "PP-DocLayout_plus-L"
        config.setdefault("paddle_layout_model_name", default_model)
        config.setdefault("external_layout_backend_name", layout_backend)
        config.setdefault("external_layout_model", config.get("paddle_layout_model_name") or default_model)
        config.setdefault("external_layout_block_source", "boxes")
        super().__init__(config)
        self.runtime = runtime or PaddleLayoutDetectionRuntime(config)
        self.last_runtime_payload = None

    def __call__(self, document: Document, provider: PdfProvider):
        if self.external_layout_json:
            return super().__call__(document, provider)

        with tempfile.TemporaryDirectory(prefix="contexture-paddle-layout-") as temp_dir:
            image_paths, page_sizes = self._save_page_images(document, Path(temp_dir))
            payload = self.runtime.run(image_paths, page_sizes=page_sizes)
            self.last_runtime_payload = payload

            sidecar_pages = self._load_pages_from_payload(payload, source="paddle_layout_runtime")
            layout_results = self._layout_results_for_pages(document.pages, sidecar_pages)
            self._layout_helper.add_blocks_to_pages(document.pages, layout_results)
            self._layout_helper.expand_layout_blocks(document)

    def _save_page_images(self, document: Document, output_dir: Path) -> tuple[list[Path], list[tuple[int, int]]]:
        image_paths: list[Path] = []
        page_sizes: list[tuple[int, int]] = []
        for sequential_index, page in enumerate(document.pages):
            image = page.get_image(highres=False)
            if image is None:
                raise ValueError(f"Cannot run Paddle layout: page {sequential_index} has no renderable image.")
            image_path = output_dir / f"page_{sequential_index:06d}.png"
            image.save(image_path)
            image_paths.append(image_path)
            page_sizes.append((int(image.size[0]), int(image.size[1])))
        return image_paths, page_sizes
